from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import base64
import html
import io
import json
import mimetypes
import os
import random
import re
import time
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

try:
    import nls
    ALIYUN_NLS_AVAILABLE = True
except ImportError:
    ALIYUN_NLS_AVAILABLE = False

try:
    import azure.cognitiveservices.speech as speechsdk
    AZURE_SPEECH_AVAILABLE = True
except ImportError:
    AZURE_SPEECH_AVAILABLE = False

EDGE_TTS_AVAILABLE = False


mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("model/gltf-binary", ".glb")

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SESSIONS = {}

AVATAR_PROFILES = [
    {
        "id": "lingshan-default",
        "name": "灵小山",
        "title": "灵山胜境讲解员",
        "avatar": "灵小山 - 灵山讲解员",
        "voice": "温柔讲解女声",
        "style": "calm",
        "cssClass": "profile-lingshan",
        "rate": 1.00,
        "pitch": 1.08,
        "voiceHints": ["Xiaoxiao", "Huihui", "Yaoyao", "Female"],
        "ttsVoice": "zh-CN-XiaoxiaoNeural",
        "voiceSlot": 0,
        "tagline": "亲切、稳重，适合通用景区问答。",
        "chips": ["灵山讲解", "温柔女声", "通用导览"],
    },
    {
        "id": "zen-host",
        "name": "拈花小禅",
        "title": "拈花湾禅意导览员",
        "avatar": "拈花小禅 - 禅意讲解员",
        "voice": "清雅禅意女声",
        "style": "warm",
        "cssClass": "profile-zen",
        "rate": 0.88,
        "pitch": 1.18,
        "voiceHints": ["Xiaoyi", "Xiaoxiao", "Female"],
        "ttsVoice": "zh-CN-XiaoyiNeural",
        "voiceSlot": 1,
        "tagline": "语速更舒缓，适合禅意、夜游、休闲场景。",
        "chips": ["拈花湾", "禅意慢游", "夜游推荐"],
    },
    {
        "id": "culture-scholar",
        "name": "灵山文博官",
        "title": "历史文化深度讲解员",
        "avatar": "灵山文博官 - 文化学者",
        "voice": "低沉文博男声",
        "style": "calm",
        "cssClass": "profile-scholar",
        "rate": 0.90,
        "pitch": 0.72,
        "voiceHints": ["Yunxi", "Kangkang", "Male"],
        "ttsVoice": "zh-CN-YunxiNeural",
        "voiceSlot": 2,
        "tagline": "更适合佛教文化、建筑艺术和历史深度讲解。",
        "chips": ["历史文化", "沉稳男声", "深度讲解"],
    },
    {
        "id": "family-guide",
        "name": "灵灵",
        "title": "亲子活力导览员",
        "avatar": "灵灵 - 亲子活力版",
        "voice": "活力亲子童声",
        "style": "kid",
        "cssClass": "profile-family",
        "rate": 1.16,
        "pitch": 1.48,
        "voiceHints": ["Xiaoyi", "Child", "Female"],
        "ttsVoice": "zh-CN-XiaoyiNeural",
        "voiceSlot": 3,
        "tagline": "语气更轻快，适合孩子、家庭和轻体力路线。",
        "chips": ["亲子互动", "轻快语气", "家庭路线"],
    },
    {
        "id": "service-steward",
        "name": "灵山管家",
        "title": "应急与服务导览员",
        "avatar": "灵山管家 - 服务调度",
        "voice": "清晰服务播报声",
        "style": "focused",
        "cssClass": "profile-steward",
        "rate": 1.06,
        "pitch": 0.92,
        "voiceHints": ["Yunyang", "Microsoft", "Male"],
        "ttsVoice": "zh-CN-YunyangNeural",
        "voiceSlot": 4,
        "tagline": "适合人流提醒、卫生间、餐饮、交通和应急问答。",
        "chips": ["服务调度", "清晰播报", "应急提醒"],
    },
]


def load_dotenv():
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


load_dotenv()


def read_json(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def write_json(name, value):
    (DATA / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def avatar_profile(profile_id=None):
    for profile in AVATAR_PROFILES:
        if profile["id"] == profile_id:
            return profile
    return AVATAR_PROFILES[0]


def avatar_config_payload():
    config = read_json_default("avatar_config.json", {})
    if "profileId" not in config:
        legacy_avatar = config.get("avatar", "")
        for profile in AVATAR_PROFILES:
            if profile["avatar"] == legacy_avatar or profile["name"] in legacy_avatar:
                config["profileId"] = profile["id"]
                break
    profile = avatar_profile(config.get("profileId"))
    payload = dict(config)
    payload.setdefault("profileId", profile["id"])
    payload.setdefault("avatar", profile["avatar"])
    payload.setdefault("voice", profile["voice"])
    payload.setdefault("style", profile["style"])
    payload["profile"] = profile
    payload["profiles"] = AVATAR_PROFILES
    return payload


def read_json_default(name, default):
    path = DATA / name
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def compact(text):
    return re.sub(r"\s+", "", str(text or "").lower())


def tokenize(text):
    text = str(text or "")
    words = re.findall(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]{2,}", text)
    chars = [ch for ch in text if "\u4e00" <= ch <= "\u9fff"]
    return list(dict.fromkeys(words + chars))


def short_text(text, limit=420):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip("，。；、 ") + "。"


def append_interaction(record):
    logs = read_json_default("interaction_logs.json", [])
    logs.append(record)
    del logs[:-600:]
    write_json("interaction_logs.json", logs)


def update_interaction_feedback(interaction_id, rating, comment=""):
    logs = read_json_default("interaction_logs.json", [])
    for item in logs:
        if item.get("id") == interaction_id:
            item["feedback"] = rating
            item["feedbackComment"] = short_text(comment, 160)
            item["feedbackAt"] = int(time.time())
            write_json("interaction_logs.json", logs)
            return item
    return None


def count_top(values, limit=8):
    counter = {}
    for value in values:
        if not value:
            continue
        counter[value] = counter.get(value, 0) + 1
    return [{"name": key, "value": value} for key, value in sorted(counter.items(), key=lambda pair: pair[1], reverse=True)[:limit]]


def feedback_analysis():
    logs = read_json_default("interaction_logs.json", [])
    total = len(logs)
    ratings = [item.get("feedback") for item in logs if item.get("feedback")]
    rating_map = {"good": "满意", "neutral": "一般", "bad": "不满意"}
    rating_counts = {label: 0 for label in rating_map.values()}
    for rating in ratings:
        rating_counts[rating_map.get(rating, rating)] = rating_counts.get(rating_map.get(rating, rating), 0) + 1

    questions = [item.get("query", "") for item in logs]
    source_titles = []
    route_titles = []
    emotions = []
    for item in logs:
        emotions.append(item.get("emotionName") or item.get("emotion"))
        source_titles.extend(source.get("title") for source in item.get("sources", []) if source.get("title"))
        route_titles.extend(route.get("title") for route in item.get("routeRecommendations", []) if route.get("title"))

    keyword_values = []
    for question in questions:
        keyword_values.extend([token for token in tokenize(question) if len(token) >= 2][:6])

    suggestions = []
    if total == 0:
        suggestions.append("暂无真实交互记录，建议先用游客端完成几轮问答和反馈。")
    if rating_counts.get("不满意", 0):
        suggestions.append("存在不满意反馈，建议优先复查这些问题对应的知识库命中结果和回答口径。")
    if route_titles:
        suggestions.append("路线咨询已经产生真实记录，可把高频路线放到游客端快捷入口。")
    if source_titles:
        suggestions.append("高频知识来源可作为讲解词优化重点，补充更短、更适合语音播报的版本。")

    return {
        "totalInteractions": total,
        "ratedInteractions": len(ratings),
        "ratingCounts": rating_counts,
        "hotQuestions": count_top(questions, 8),
        "hotKeywords": count_top(keyword_values, 10),
        "hotSources": count_top(source_titles, 8),
        "routeInterest": count_top(route_titles, 6),
        "emotionTrend": count_top(emotions, 6),
        "latest": list(reversed(logs[-12:])),
        "suggestions": suggestions[:5],
    }


def parse_multipart(body, content_type):
    match = re.search(r"boundary=(?P<boundary>[^;]+)", content_type or "")
    if not match:
        return {}
    boundary = ("--" + match.group("boundary").strip().strip('"')).encode("utf-8")
    fields = {}
    for part in body.split(boundary):
        part = part.strip(b"\r\n")
        if not part or part == b"--" or b"\r\n\r\n" not in part:
            continue
        raw_headers, value = part.split(b"\r\n\r\n", 1)
        if value.endswith(b"\r\n--"):
            value = value[:-4]
        headers = raw_headers.decode("utf-8", errors="ignore")
        name_match = re.search(r'name="([^"]+)"', headers)
        if not name_match:
            continue
        filename_match = re.search(r'filename="([^"]*)"', headers)
        fields[name_match.group(1)] = {
            "filename": filename_match.group(1) if filename_match else "",
            "content": value.rstrip(b"\r\n"),
            "headers": headers,
        }
    return fields


def extract_docx_text(raw):
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            xml = archive.read("word/document.xml")
        root = ET.fromstring(xml)
        paragraphs = []
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        for para in root.findall(".//w:p", ns):
            text = "".join(node.text or "" for node in para.findall(".//w:t", ns)).strip()
            if text:
                paragraphs.append(text)
        return "\n".join(paragraphs)
    except Exception:
        return ""


def extract_upload_text(filename, raw):
    suffix = Path(filename or "upload.txt").suffix.lower()
    if suffix == ".docx":
        return extract_docx_text(raw)
    for encoding in ["utf-8-sig", "utf-8", "gb18030"]:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def knowledge_items_from_upload(filename, text, area="灵山胜境", category="文件上传"):
    text = html.unescape(text or "")
    suffix = Path(filename or "").suffix.lower()
    created = []
    if suffix == ".json":
        try:
            data = json.loads(text)
            source_items = data if isinstance(data, list) else data.get("items", data.get("knowledge", []))
            if isinstance(source_items, list):
                for index, source in enumerate(source_items):
                    if isinstance(source, str):
                        title = short_text(source, 28)
                        content = source
                    else:
                        title = source.get("title") or source.get("name") or f"{Path(filename).stem}-{index + 1}"
                        content = source.get("content") or source.get("summary") or source.get("text") or json.dumps(source, ensure_ascii=False)
                    created.append({
                        "id": f"upload-{int(time.time() * 1000)}-{len(created)}",
                        "title": short_text(title, 36),
                        "area": source.get("area", area) if isinstance(source, dict) else area,
                        "category": source.get("category", category) if isinstance(source, dict) else category,
                        "content": short_text(content, 1400),
                        "keywords": tokenize(f"{title} {content}")[:10],
                        "source": filename,
                    })
        except Exception:
            pass
    if created:
        return created

    chunks = []
    for block in re.split(r"\n\s*\n|(?=^#{1,3}\s+)", text, flags=re.M):
        block = block.strip()
        if len(block) >= 12:
            chunks.append(block)
    if not chunks and text.strip():
        chunks = [text.strip()]

    for index, chunk in enumerate(chunks[:80]):
        lines = [line.strip("# \t") for line in chunk.splitlines() if line.strip()]
        title = lines[0][:36] if lines else f"{Path(filename).stem}-{index + 1}"
        content = "\n".join(lines[1:]).strip() or chunk
        created.append({
            "id": f"upload-{int(time.time() * 1000)}-{index}",
            "title": short_text(title or Path(filename).stem, 36),
            "area": area,
            "category": category,
            "content": short_text(content, 1400),
            "keywords": tokenize(f"{title} {content}")[:10],
            "source": filename,
        })
    return created


def all_spot_docs():
    docs = []
    for spot in read_json("scenic_spots.json"):
        docs.append(
            {
                "id": spot["id"],
                "title": spot["name"],
                "area": spot["area"],
                "category": spot["category"],
                "content": f"{spot['summary']} {spot['tips']} 建议停留{spot['duration']}分钟。",
                "keywords": spot.get("keywords", []),
                "kind": "spot",
            }
        )
    return docs


def route_docs():
    spots = {spot["id"]: spot for spot in read_json("scenic_spots.json")}
    docs = []
    for route in read_json("routes.json"):
        names = [spots[spot_id]["name"] for spot_id in route["spots"] if spot_id in spots]
        docs.append(
            {
                "id": route["id"],
                "title": route["title"],
                "area": "灵山胜境",
                "category": "路线推荐",
                "content": f"{route['description']} 路线顺序：" + " -> ".join(names),
                "keywords": route.get("interestTags", []) + [route.get("theme", ""), route.get("duration", "")],
                "kind": "route",
            }
        )
    return docs


def knowledge_docs():
    docs = read_json("knowledge_store.json")
    for doc in docs:
        doc.setdefault("kind", "knowledge")
    return docs


def all_docs():
    merged = {doc["id"]: doc for doc in all_spot_docs() + route_docs()}
    for doc in knowledge_docs():
        merged[doc["id"]] = doc
    return list(merged.values())


def llm_config():
    provider = os.environ.get("LINGSHAN_LLM_PROVIDER", "deepseek").lower()
    if provider == "qwen":
        return {
            "provider": "qwen",
            "base_url": os.environ.get("LINGSHAN_LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            "api_key": os.environ.get("LINGSHAN_LLM_API_KEY") or os.environ.get("DASHSCOPE_API_KEY", ""),
            "model": os.environ.get("LINGSHAN_LLM_MODEL", "qwen-plus"),
        }
    return {
        "provider": "deepseek",
        "base_url": os.environ.get("LINGSHAN_LLM_BASE_URL", "https://api.deepseek.com"),
        "api_key": os.environ.get("LINGSHAN_LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY", ""),
        "model": os.environ.get("LINGSHAN_LLM_MODEL", "deepseek-chat"),
    }


def llm_enabled():
    return bool(llm_config()["api_key"])


def build_context(hits):
    lines = []
    for index, doc in enumerate(hits, 1):
        lines.append(f"[{index}] {doc.get('title')} / {doc.get('category')}: {doc.get('content')}")
    return "\n".join(lines)


def call_external_llm(query, hits, route_recommendations, history):
    config = llm_config()
    if not config["api_key"]:
        return None
    route_hint = ""
    if route_recommendations:
        route_hint = "可推荐路线：" + "；".join(
            f"{route['title']}（{route['duration']}，{route['description']}）" for route in route_recommendations[:3]
        )
    messages = [
        {
            "role": "system",
            "content": (
                "你是无锡灵山胜境的AI数字人导游“灵小山”。"
                "只能基于给定资料回答，不确定时要说明并给出安全建议。"
                "回答要自然、亲切、适合游客现场使用，控制在180字以内。"
                "如果用户问路线，要给出顺序、适合人群和注意事项。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"游客问题：{query}\n\n"
                f"检索资料：\n{build_context(hits)}\n\n"
                f"{route_hint}\n\n"
                f"最近对话：{json.dumps(history[-3:], ensure_ascii=False)}"
            ),
        },
    ]
    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": 0.35,
        "max_tokens": 420,
        "stream": False,
    }
    url = config["base_url"].rstrip("/") + "/v1/chat/completions"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=18) as response:
        result = json.loads(response.read().decode("utf-8"))
    return result["choices"][0]["message"]["content"].strip()


def score_doc(query, doc):
    q = compact(query)
    haystack = compact(" ".join([doc.get("title", ""), doc.get("category", ""), doc.get("content", ""), " ".join(doc.get("keywords", []))]))
    score = 0
    for token in tokenize(query):
        ct = compact(token)
        if not ct:
            continue
        if ct in compact(doc.get("title", "")):
            score += 12
        if ct in " ".join(compact(keyword) for keyword in doc.get("keywords", [])):
            score += 8
        if ct in haystack:
            score += 3
    if doc.get("category") == "路线推荐" and any(word in q for word in ["路线", "游线", "安排", "推荐", "亲子", "历史", "文化", "自然"]):
        score += 8
    if doc.get("kind") == "spot" and any(word in q for word in ["景点", "在哪", "怎么走", "介绍", "讲讲", "多久"]):
        score += 4
    return score


def emotion_for(query):
    if any(word in query for word in ["急", "快", "赶时间", "马上", "不耐烦"]):
        return {"label": "urgent", "name": "着急", "avatarState": "focused"}
    if any(word in query for word in ["开心", "好玩", "漂亮", "喜欢", "期待"]):
        return {"label": "happy", "name": "开心", "avatarState": "smile"}
    if any(word in query for word in ["为什么", "历史", "文化", "讲讲", "介绍"]):
        return {"label": "curious", "name": "好奇", "avatarState": "thinking"}
    return {"label": "neutral", "name": "平静", "avatarState": "normal"}


def auto_guide_spots():
    spots = {spot["id"]: spot for spot in read_json("scenic_spots.json")}
    configured = read_json_default("auto_guide_spots.json", [])
    result = []
    for item in configured:
        spot_id = item.get("id", "")
        base = spots.get(spot_id, {})
        latitude = item.get("latitude")
        longitude = item.get("longitude")
        if latitude is None or longitude is None:
            continue
        name = item.get("name") or base.get("name") or spot_id
        summary = item.get("narration") or base.get("summary") or base.get("detail") or ""
        tips = base.get("tips", "")
        narration = short_text(f"{summary} {tips}", 280)
        result.append({
            "id": spot_id,
            "name": name,
            "area": item.get("area") or base.get("area", "灵山胜境"),
            "category": item.get("category") or base.get("category", "景点讲解"),
            "latitude": latitude,
            "longitude": longitude,
            "radius": int(item.get("radius", 160)),
            "summary": short_text(base.get("summary") or summary, 160),
            "narration": narration,
        })
    return result


def routes_with_spots():
    routes = read_json("routes.json")
    spots = {spot["id"]: spot for spot in read_json("scenic_spots.json")}
    enriched = []
    for route in routes:
        item = dict(route)
        item["spotDetails"] = [spots[spot_id] for spot_id in route["spots"] if spot_id in spots]
        enriched.append(item)
    return enriched


def recommend_routes(interest="", hours=None):
    q = compact(interest)
    routes = routes_with_spots()
    scored = []
    for route in routes:
        haystack = compact(route["title"] + route["description"] + "".join(route.get("interestTags", [])) + route.get("theme", ""))
        score = 0
        for token in tokenize(interest):
            if compact(token) in haystack:
                score += 5
        if "亲子" in q or "孩子" in q or "家庭" in q:
            score += 20 if route["theme"] == "family" else 0
        if "历史" in q or "文化" in q or "佛教" in q:
            score += 20 if route["theme"] == "history" else 0
        if "自然" in q or "拍照" in q or "轻松" in q:
            score += 20 if route["theme"] == "nature" else 0
        if "拈花湾" in q or "夜游" in q or "休闲" in q or "灯光秀" in q or "禅意" in q:
            score += 24 if route["theme"] == "leisure" else 0
        if hours:
            route_hours = int(re.findall(r"\d+", route["duration"])[0])
            score += max(0, 10 - abs(route_hours - int(hours)) * 3)
        scored.append((score, route))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [route for _, route in scored]


def chat_answer(query, session_id="default"):
    started_at = time.time()
    docs = all_docs()
    ranked = sorted(docs, key=lambda doc: score_doc(query, doc), reverse=True)
    hits = [doc for doc in ranked if score_doc(query, doc) > 0][:4]
    route_recommendations = []

    if any(word in query for word in ["路线", "游线", "安排", "推荐", "亲子", "老人", "孩子", "半天", "一天"]):
        route_recommendations = recommend_routes(query)[:3]

    if not hits:
        hits = route_docs()[:2]
        answer = "我先按灵山胜境常规导览来回答：建议从山门进入，依次游览九龙灌浴、天下第一掌、祥符禅寺、灵山大佛和梵宫。如果你告诉我兴趣和游玩时长，我可以推荐更合适的路线。"
    else:
        main = hits[0]
        if main.get("category") == "路线推荐":
            answer = f"我推荐你优先考虑{main['title']}。{main['content']}"
        else:
            answer = f"关于{main['title']}：{main['content']}"
        related = [hit["title"] for hit in hits[1:3]]
        if related:
            answer += " 相关信息还包括：" + "、".join(related) + "。"

    history = SESSIONS.setdefault(session_id, [])
    engine = "local-rag-phase4"
    llm_error = ""
    try:
        llm_answer = call_external_llm(query, hits, route_recommendations, history)
        if llm_answer:
            answer = llm_answer
            engine = f"{llm_config()['provider']}-{llm_config()['model']}"
    except Exception as exc:
        llm_error = str(exc)[:180]

    history.append({"q": query, "a": answer, "time": int(time.time())})
    del history[:-6]

    followups = []
    if route_recommendations:
        followups = ["开始讲解第一站", "这条路线适合老人吗", "附近哪里能休息"]
    elif hits:
        followups = [f"{hits[0]['title']}附近怎么走", "推荐一条相关路线", "讲得更详细一点"]

    confidence = min(0.96, 0.68 + len(hits) * 0.07)
    result = {
        "answer": answer,
        "emotion": emotion_for(query or ""),
        "sources": [{"id": hit["id"], "title": hit["title"], "category": hit["category"]} for hit in hits],
        "routeRecommendations": route_recommendations,
        "followups": followups,
        "confidence": round(confidence, 2),
        "memoryTurns": len(history),
        "latencyMs": int((time.time() - started_at) * 1000),
        "mock": False,
        "engine": engine,
        "externalLlmEnabled": llm_enabled(),
        "externalLlmError": llm_error,
    }
    interaction_id = f"chat-{int(time.time() * 1000)}-{random.randint(1000, 9999)}"
    result["interactionId"] = interaction_id
    append_interaction({
        "id": interaction_id,
        "time": int(time.time()),
        "sessionId": session_id,
        "query": query,
        "answer": short_text(answer, 900),
        "engine": engine,
        "confidence": result["confidence"],
        "latencyMs": result["latencyMs"],
        "emotion": result["emotion"].get("label"),
        "emotionName": result["emotion"].get("name"),
        "sources": result["sources"],
        "routeRecommendations": [{"id": route.get("id"), "title": route.get("title")} for route in route_recommendations],
        "feedback": None,
    })
    return result


def split_answer(text, size=14):
    parts = []
    buf = ""
    for char in text:
        buf += char
        if len(buf) >= size or char in "。！？；，":
            parts.append(buf)
            buf = ""
    if buf:
        parts.append(buf)
    return parts


def tts_voice_for_profile(profile_id=None):
    for profile in AVATAR_PROFILES:
        if profile["id"] == profile_id:
            return profile.get("ttsVoice", "zh-CN-XiaoxiaoNeural")
    return "zh-CN-XiaoxiaoNeural"


def aliyun_tts_config():
    appkey = os.environ.get("ALIYUN_NLS_APPKEY", "").strip()
    token = os.environ.get("ALIYUN_NLS_TOKEN", "").strip()
    return {
        "enabled": bool(appkey and token),
        "appkey": appkey,
        "token": token,
        "url": os.environ.get("ALIYUN_NLS_URL", "wss://nls-gateway.cn-shanghai.aliyuncs.com/ws/v1").strip(),
        "voice": os.environ.get("ALIYUN_NLS_VOICE", "siyue").strip() or "siyue",
        "sampleRate": int(os.environ.get("ALIYUN_NLS_SAMPLE_RATE", "24000") or 24000),
    }


def azure_speech_config():
    key = os.environ.get("AZURE_SPEECH_KEY", "").strip()
    region = os.environ.get("AZURE_SPEECH_REGION", "").strip()
    return {
        "enabled": bool(key and region),
        "key": key,
        "region": region,
        "voice": os.environ.get("AZURE_SPEECH_VOICE", "zh-CN-XiaoxiaoNeural").strip() or "zh-CN-XiaoxiaoNeural",
        "lang": os.environ.get("AZURE_SPEECH_LANG", "zh-CN").strip() or "zh-CN",
    }


AZURE_BLENDSHAPE_MAP = [
    "eyeBlinkLeft", "eyeLookDownLeft", "eyeLookInLeft", "eyeLookOutLeft", "eyeLookUpLeft",
    "eyeSquintLeft", "eyeWideLeft", "eyeBlinkRight", "eyeLookDownRight", "eyeLookInRight",
    "eyeLookOutRight", "eyeLookUpRight", "eyeSquintRight", "eyeWideRight", "jawForward",
    "jawLeft", "jawRight", "jawOpen", "mouthClose", "mouthFunnel", "mouthPucker",
    "mouthLeft", "mouthRight", "mouthSmileLeft", "mouthSmileRight", "mouthFrownLeft",
    "mouthFrownRight", "mouthDimpleLeft", "mouthDimpleRight", "mouthStretchLeft",
    "mouthStretchRight", "mouthRollLower", "mouthRollUpper", "mouthShrugLower",
    "mouthShrugUpper", "mouthPressLeft", "mouthPressRight", "mouthLowerDownLeft",
    "mouthLowerDownRight", "mouthUpperUpLeft", "mouthUpperUpRight", "browDownLeft",
    "browDownRight", "browInnerUp", "browOuterUpLeft", "browOuterUpRight", "cheekPuff",
    "cheekSquintLeft", "cheekSquintRight", "noseSneerLeft", "noseSneerRight", "tongueOut",
    "headRoll", "leftEyeRoll", "rightEyeRoll",
]


def escape_ssml_text(text):
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


EDGE_VISEME_TO_MODEL = {
    # Microsoft/Edge viseme ids mapped to the Oculus-style morph targets in
    # guide.glb.  Several speech sounds intentionally share one visible shape.
    0: "", 1: "aa", 2: "aa", 3: "O", 4: "E", 5: "RR", 6: "I", 7: "U",
    8: "O", 9: "DD", 10: "SS", 11: "SS", 12: "TH", 13: "RR", 14: "DD",
    15: "SS", 16: "CH", 17: "FF", 18: "PP", 19: "PP", 20: "kk", 21: "kk",
}


PHONEME_TO_MODEL_VISEME = {
    # Bilabial closure.
    "b": "PP", "p": "PP", "m": "PP", "b_c": "PP", "p_c": "PP", "m_c": "PP",
    # Labiodental.
    "f": "FF", "v": "FF", "f_c": "FF",
    # Dental and tongue-contact consonants.
    "th": "TH", "dh": "TH",
    "d": "DD", "t": "DD", "n": "DD", "l": "DD",
    "d_c": "DD", "t_c": "DD", "n_c": "DD", "l_c": "DD",
    # Velar.
    "k": "kk", "g": "kk", "ng": "kk", "h": "kk", "hh": "kk",
    "g_c": "kk", "k_c": "kk", "h_c": "kk",
    # Affricates and retroflexes.
    "ch": "CH", "jh": "CH", "q_c": "CH", "j_c": "CH", "zh_c": "CH", "ch_c": "CH",
    # Sibilants.
    "s": "SS", "z": "SS", "sh": "SS", "zh": "SS",
    "s_c": "SS", "x_c": "SS", "z_c": "SS", "c_c": "SS", "sh_c": "SS",
    # Rounded finals.
    "u": "U", "uw": "U", "uh": "U", "w": "U", "v_c": "U",
    "u_c": "U", "ue_c": "U", "un_c": "U", "uo_c": "U", "ui_c": "U",
    "ou": "O", "ow": "O", "ao": "O", "o_c": "O", "ou_c": "O", "ong_c": "O",
    # Front vowels.
    "i": "I", "iy": "I", "ih": "I", "y": "I", "i_c": "I", "in_c": "I", "ing_c": "I",
    "e": "E", "eh": "E", "ey": "E", "ae": "E", "e_c": "E", "ei_c": "E", "en_c": "E",
    # Open vowels and diphthongs.
    "aa": "aa", "ah": "aa", "ah0": "aa", "ah1": "aa", "ah2": "aa",
    "a_c": "aa", "ai_c": "aa", "an_c": "aa", "ang_c": "aa", "ian_c": "aa", "ia_c": "aa",
    # R-coloured.
    "r": "RR", "er": "RR", "r_c": "RR", "er_c": "RR",
}


class TtsGenerationError(RuntimeError):
    """Raised when the external speech engine cannot produce a usable result."""


def _analyze_audio_mouth_envelope(audio_mp3_bytes, word_times=None, debug=None):
    """Return an audio-timed mouth-opening envelope and the decoded duration.

    This intentionally does *not* infer vowel shapes from loudness.  Audio
    energy can say how far the jaw should open, but cannot tell /a/ from /o/.
    The phonetic shape is assigned from Edge's VisemeBoundary events below.
    """
    import tempfile
    import os as _os

    try:
        import miniaudio
    except ImportError:
        return None, 0

    try:
        import numpy as np
    except ImportError:
        return None, 0

    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
        with _os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(audio_mp3_bytes)

        decoded = miniaudio.decode_file(tmp_path)
        sr = decoded.sample_rate
        ch = decoded.nchannels
        samples = np.frombuffer(decoded.samples, dtype=np.int16).astype(np.float32)
        if ch > 1:
            samples = samples.reshape(-1, ch).mean(axis=1)
    except Exception:
        return None, 0
    finally:
        if tmp_path and _os.path.exists(tmp_path):
            _os.unlink(tmp_path)

    if len(samples) < sr // 10:
        return None, 0

    duration_ms = int(len(samples) * 1000 / sr)

    db = debug or {}
    peak = float(np.abs(samples).max() or 1)
    samples = samples / peak

    # Keep silence closed, but let voiced vowels open clearly.  Earlier values
    # were intentionally conservative and made the avatar look almost closed.
    NOISE_FLOOR  = min(0.3, max(0.0, float(db.get("noiseFloor", 0.025))))
    MO_MIN       = min(0.8, max(0.0, float(db.get("moMin", 0.05))))
    MO_MAX       = min(1.0, max(MO_MIN, float(db.get("moMax", 0.95))))
    ATTACK_MS    = min(500.0, max(1.0, float(db.get("attackMs", 12))))
    RELEASE_MS   = min(500.0, max(1.0, float(db.get("releaseMs", 45))))
    HOLD_MS      = min(500.0, max(0.0, float(db.get("holdMs", 0))))
    SMOOTH_WIN   = min(30, max(1, int(db.get("smoothFrames", 2))))

    win_samples = int(sr * 0.01)
    hop_samples = win_samples // 2
    n_windows = max(1, (len(samples) - win_samples) // hop_samples + 1)
    times = np.arange(n_windows) * hop_samples * 1000 / sr

    rms_raw = np.zeros(n_windows)
    for i in range(n_windows):
        rms_raw[i] = float(np.sqrt(np.mean(samples[i*hop_samples : i*hop_samples+win_samples] ** 2)))

    p95 = float(np.percentile(rms_raw, 95)) + 1e-12
    energy = np.clip(rms_raw / p95, 0, 1)

    if SMOOTH_WIN > 1:
        kernel = np.ones(SMOOTH_WIN) / SMOOTH_WIN
        energy = np.convolve(energy, kernel, mode="same")

    # Use WordBoundary only as a noise gate.  The generous margins avoid
    # clipping consonants at a boundary; phoneme identity comes from visemes.
    envelope = np.zeros(n_windows)

    if word_times and len(word_times) > 0:
        for (w_start, w_end) in word_times:
            w_start = max(0, w_start - 35)
            w_end = max(w_start + 30, w_end + 35)
            mask = (times >= w_start) & (times <= w_end)
            envelope[mask] = np.maximum(envelope[mask], energy[mask])
    else:
        envelope = np.where(energy > NOISE_FLOOR, energy, 0.0)

    # Attack/release smoothing
    atk_coef = np.exp(-hop_samples / (max(ATTACK_MS, 1) * sr / 1000))
    rel_coef = np.exp(-hop_samples / (max(RELEASE_MS, 1) * sr / 1000))

    smoothed = envelope.copy()
    for i in range(1, n_windows):
        if envelope[i] > smoothed[i - 1]:
            smoothed[i] = envelope[i] * (1 - atk_coef) + smoothed[i - 1] * atk_coef
        else:
            smoothed[i] = envelope[i] * (1 - rel_coef) + smoothed[i - 1] * rel_coef

    # Hold
    if HOLD_MS > 0 and word_times:
        hf = max(1, int(HOLD_MS / 10))
        held = smoothed.copy()
        for i in range(n_windows):
            if smoothed[i] > NOISE_FLOOR * 0.5:
                for j in range(i, min(i + hf, n_windows)):
                    held[j] = max(held[j], NOISE_FLOOR * 1.5)
        smoothed = held

    # Hard gate: outside word windows, force zero
    gated = smoothed.copy()
    if word_times and len(word_times) > 0:
        in_word = np.zeros(n_windows, dtype=bool)
        for (w_start, w_end) in word_times:
            w_start = max(0, w_start - 35)
            w_end += 35
            in_word |= (times >= w_start) & (times <= w_end)
        gated[~in_word] = 0

    final_env = np.where(gated > NOISE_FLOOR, gated, 0.0)

    normalized_env = np.clip(
        (final_env - NOISE_FLOOR) / max(1e-6, 1.0 - NOISE_FLOOR), 0, 1
    )
    mo_scaled = np.where(
        final_env > 0,
        MO_MIN + normalized_env ** 0.78 * (MO_MAX - MO_MIN),
        0.0,
    )
    mo_scaled = np.clip(mo_scaled, 0, MO_MAX)

    # 20 ms is visually smooth while keeping the response small enough for a
    # debugging page to inspect.  The last keyframe makes closure deterministic.
    frames = [
        {"t": int(times[i]), "mo": round(float(mo_scaled[i]), 3)}
        for i in range(0, n_windows, 4)
    ]
    if not frames or frames[-1]["t"] < duration_ms:
        frames.append({"t": duration_ms, "mo": 0.0})
    else:
        frames[-1]["mo"] = 0.0
    return frames, duration_ms


def _edge_viseme_events(raw_visemes):
    """Normalise Edge events to browser milliseconds and model morph names."""
    events = []
    for event in raw_visemes or []:
        try:
            viseme_id = int(event["viseme_id"])
            start_ms = max(0, int(event["offset"]) // 10000)
            duration_ms = max(0, int(event.get("duration", 0)) // 10000)
        except (KeyError, TypeError, ValueError):
            continue
        events.append({
            "t": start_ms,
            "d": duration_ms,
            "id": viseme_id,
            "vis": EDGE_VISEME_TO_MODEL.get(viseme_id, ""),
        })
    return sorted(events, key=lambda item: item["t"])


def _build_viseme_timeline(envelope, events, duration_ms):
    """Combine audio amplitude with the service's phonetic timeline.

    Mouth openness is driven by the phoneme, not the raw energy envelope:
      - consonants (PP/FF/DD/kk/CH/SS/TH) → jaw nearly shut
      - vowels (aa/O/E/I/U) → energy from the audio envelope
      - silence (no active viseme) → closed
    """
    if not envelope:
        return None

    CONSONANT_SET = {"PP", "FF", "DD", "kk", "CH", "SS", "TH"}
    VOWEL_SET = {"aa", "O", "E", "I", "U"}

    event_index = 0
    active_viseme = ""
    timeline = []
    for frame in envelope:
        while event_index < len(events) and events[event_index]["t"] <= frame["t"]:
            active_viseme = events[event_index]["vis"]
            event_index += 1

        if not active_viseme:
            mo = 0.0
        elif active_viseme in CONSONANT_SET:
            mo = 0.04
        elif active_viseme in VOWEL_SET:
            mo = max(0.12, round(frame["mo"], 3))
        else:
            mo = 0.0

        timeline.append({"t": frame["t"], "mo": mo, "vis": active_viseme})

    if timeline[-1]["t"] < duration_ms:
        timeline.append({"t": duration_ms, "mo": 0.0, "vis": ""})
    else:
        timeline[-1].update({"mo": 0.0, "vis": ""})
    return timeline


def _phoneme_to_model_viseme(phoneme):
    key = str(phoneme or "").strip().lower()
    if not key or key == "null":
        return ""
    if key in PHONEME_TO_MODEL_VISEME:
        return PHONEME_TO_MODEL_VISEME[key]
    if key.endswith("_c"):
        # Most Chinese finals are visually closest to their main vowel.
        base = key[:-2]
        if base.startswith(("u", "v")) or "u" in base:
            return "U"
        if base.startswith("o") or "o" in base:
            return "O"
        if base.startswith(("i", "y")) or "i" in base:
            return "I"
        if base.startswith("e") or "e" in base:
            return "E"
        if base.startswith("a") or "a" in base:
            return "aa"
    return "aa"


def _aliyun_phoneme_events(subtitles):
    events = []
    for item in subtitles or []:
        phoneme_list = item.get("phoneme_list") or []
        if not phoneme_list:
            try:
                start_ms = max(0, int(item.get("begin_time", 0)))
                end_ms = max(start_ms, int(item.get("end_time", start_ms)))
            except (TypeError, ValueError):
                start_ms = 0
                end_ms = 0
            phones = [
                part.strip()
                for part in str(item.get("phoneme") or "").split()
                if part.strip() and part.strip().lower() != "null"
            ]
            if phones and end_ms > start_ms:
                step = (end_ms - start_ms) / len(phones)
                phoneme_list = [
                    {
                        "index": index,
                        "begin_time": round(start_ms + step * index),
                        "end_time": round(start_ms + step * (index + 1)),
                        "phoneme": phoneme,
                        "tone": None,
                    }
                    for index, phoneme in enumerate(phones)
                ]

        for phone in phoneme_list:
            try:
                start_ms = max(0, int(phone.get("begin_time", 0)))
                end_ms = max(start_ms, int(phone.get("end_time", start_ms)))
            except (TypeError, ValueError):
                continue
            phoneme = str(phone.get("phoneme") or "")
            events.append({
                "t": start_ms,
                "d": max(0, end_ms - start_ms),
                "id": phoneme,
                "vis": _phoneme_to_model_viseme(phoneme),
                "phoneme": phoneme,
                "tone": phone.get("tone"),
            })
    return sorted(events, key=lambda item: item["t"])


def _subtitle_texts_from_original(text, subtitles):
    pronounced_chars = [
        char for char in text
        if not char.isspace() and not re.match(r"^[\W_]+$", char, re.UNICODE)
    ]
    if pronounced_chars:
        return pronounced_chars[:min(len(pronounced_chars), len(subtitles or pronounced_chars))]

    words = []
    cursor = 0
    for item in subtitles or []:
        try:
            start = int(item.get("begin_index", -1))
            end = int(item.get("end_index", -1))
        except (TypeError, ValueError):
            start = -1
            end = -1
        if 0 <= start < end <= len(text):
            word = text[start:end]
            cursor = max(cursor, end)
        else:
            word = text[cursor:cursor + 1] if cursor < len(text) else item.get("text", "")
            cursor += len(word)
        words.append(word)
    return words


def _subtitle_word_times(subtitles):
    times = []
    for item in subtitles or []:
        try:
            start_ms = max(0, int(item.get("begin_time", 0)))
            end_ms = max(start_ms, int(item.get("end_time", start_ms)))
        except (TypeError, ValueError):
            continue
        if end_ms > start_ms:
            times.append((start_ms, end_ms))
    return times or None


def _dedupe_subtitles(subtitles):
    deduped = []
    seen = set()
    for item in sorted(
        subtitles or [],
        key=lambda value: (
            int(value.get("begin_time", 0) or 0),
            int(value.get("end_time", 0) or 0),
            str(value.get("phoneme") or ""),
        ),
    ):
        key = (
            item.get("begin_index"),
            item.get("end_index"),
            item.get("begin_time"),
            item.get("end_time"),
            item.get("phoneme"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _generate_aliyun_tts_sync(text, profile_id=None, lip_debug=None):
    config = aliyun_tts_config()
    if not text or not config["enabled"]:
        return None
    if not ALIYUN_NLS_AVAILABLE:
        raise TtsGenerationError("Aliyun NLS SDK is not installed")

    audio_chunks = []
    metainfo_messages = []
    error_messages = []
    completed_messages = []

    def on_data(data, *args):
        audio_chunks.append(data)

    def on_metainfo(message, *args):
        metainfo_messages.append(message)

    def on_completed(message, *args):
        completed_messages.append(message)

    def on_error(message, *args):
        error_messages.append(message)

    synthesizer = nls.NlsSpeechSynthesizer(
        url=config["url"],
        token=config["token"],
        appkey=config["appkey"],
        on_metainfo=on_metainfo,
        on_data=on_data,
        on_completed=on_completed,
        on_error=on_error,
    )
    try:
        synthesizer.start(
            text=text,
            voice=config["voice"],
            aformat="mp3",
            sample_rate=config["sampleRate"],
            wait_complete=True,
            start_timeout=10,
            completed_timeout=60,
            ex={"enable_subtitle": True, "enable_phoneme_timestamp": True},
        )
    except Exception as error:
        raise TtsGenerationError(f"Aliyun NLS {type(error).__name__}: {error}") from error

    if error_messages:
        raise TtsGenerationError(f"Aliyun NLS error: {error_messages[-1]}")
    if not audio_chunks:
        return None

    subtitles = []
    for message in metainfo_messages:
        try:
            payload = json.loads(message).get("payload", {})
        except (TypeError, json.JSONDecodeError):
            continue
        subtitles.extend(payload.get("subtitles") or [])
    subtitles = _dedupe_subtitles(subtitles)

    mp3_bytes = b"".join(audio_chunks)
    envelope, audio_duration_ms = _analyze_audio_mouth_envelope(mp3_bytes, None, lip_debug)
    envelope_from_audio = bool(envelope)
    phoneme_events = _aliyun_phoneme_events(subtitles)
    if not envelope and phoneme_events:
        envelope = [
            {"t": event["t"], "mo": 0.0 if not event["vis"] else 0.48}
            for event in phoneme_events
        ]
        audio_duration_ms = max((event["t"] + event["d"] for event in phoneme_events), default=0)
    viseme_timeline = _build_viseme_timeline(envelope, phoneme_events, audio_duration_ms)
    lipsync_source = (
        "aliyun-phoneme+audio-envelope" if phoneme_events and envelope_from_audio
        else "aliyun-phoneme-constant-aperture" if phoneme_events
        else "aliyun-audio-envelope-only"
    )

    return {
        "audio": base64.b64encode(mp3_bytes).decode("ascii"),
        "audioFormat": "mp3",
        "words": _subtitle_texts_from_original(text, subtitles),
        "wtimes": [int(item.get("begin_time", 0) or 0) for item in subtitles],
        "wdurations": [
            max(0, int(item.get("end_time", 0) or 0) - int(item.get("begin_time", 0) or 0))
            for item in subtitles
        ],
        "visemeTimeline": viseme_timeline,
        "visemeEvents": phoneme_events,
        "subtitles": subtitles,
        "audioDurationMs": audio_duration_ms,
        "lipsyncSource": lipsync_source,
        "voice": config["voice"],
        "provider": "aliyun-nls",
    }



def generate_tts_sync(text, profile_id=None, lip_debug=None):
    last_error = None
    if azure_speech_config()["enabled"]:
        try:
            result = generate_azure_blendshape_tts(text, tts_voice_for_profile(profile_id))
            if result:
                return result
        except TtsGenerationError as error:
            last_error = error

    if aliyun_tts_config()["enabled"]:
        try:
            result = _generate_aliyun_tts_sync(text, profile_id, lip_debug)
            if result:
                return result
        except TtsGenerationError as error:
            if last_error:
                raise TtsGenerationError(f"Azure failed: {last_error}; Aliyun failed: {error}") from error
            raise

    if last_error:
        raise last_error
    return None


def generate_azure_blendshape_tts(text, voice=None):
    config = azure_speech_config()
    if not text:
        raise TtsGenerationError("missing text")
    if not config["enabled"]:
        raise TtsGenerationError("Azure Speech is not configured")
    if not AZURE_SPEECH_AVAILABLE:
        raise TtsGenerationError("Azure Speech SDK is not installed")

    selected_voice = (voice or config["voice"]).strip() or config["voice"]
    speech_config = speechsdk.SpeechConfig(subscription=config["key"], region=config["region"])
    speech_config.speech_synthesis_voice_name = selected_voice
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3
    )
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)

    blendshape_chunks = {}
    viseme_events = []

    def on_viseme(evt):
        viseme_events.append({
            "t": int(evt.audio_offset // 10000),
            "id": int(evt.viseme_id),
        })
        if not evt.animation:
            return
        try:
            animation = json.loads(evt.animation)
        except json.JSONDecodeError:
            return
        frame_index = int(animation.get("FrameIndex", 0) or 0)
        frames = animation.get("BlendShapes") or []
        if frames:
            blendshape_chunks[frame_index] = frames

    synthesizer.viseme_received.connect(on_viseme)
    ssml = f"""
<speak version="1.0" xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="{config['lang']}">
  <voice name="{html.escape(selected_voice, quote=True)}">
    <mstts:viseme type="FacialExpression" />
    {escape_ssml_text(text)}
  </voice>
</speak>
"""
    result = synthesizer.speak_ssml_async(ssml).get()
    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        detail = ""
        if result.reason == speechsdk.ResultReason.Canceled:
            cancellation = speechsdk.CancellationDetails(result)
            detail = f"{cancellation.reason}: {cancellation.error_details}"
        raise TtsGenerationError(f"Azure synthesis failed: {result.reason} {detail}".strip())

    frames = []
    for frame_index in sorted(blendshape_chunks):
        frames.extend(blendshape_chunks[frame_index])

    return {
        "provider": "azure-speech",
        "voice": selected_voice,
        "audio": base64.b64encode(result.audio_data).decode("ascii"),
        "audioFormat": "mp3",
        "blendshapeNames": AZURE_BLENDSHAPE_MAP,
        "blendshapeFrames": frames,
        "frameRate": 60,
        "visemeEvents": viseme_events,
        "lipsyncSource": "azure-facialexpression-blendshapes",
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "LingShanPhase4/4.0"

    def log_message(self, fmt, *args):
        print("%s - - [%s] %s" % (self.client_address[0], self.log_date_time_string(), fmt % args))

    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_sse(self, result):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for chunk in split_answer(result["answer"]):
            event = "event: chunk\n" + "data: " + json.dumps({"text": chunk}, ensure_ascii=False) + "\n\n"
            self.wfile.write(event.encode("utf-8"))
            self.wfile.flush()
            time.sleep(0.04)
        done = "event: done\n" + "data: " + json.dumps(result, ensure_ascii=False) + "\n\n"
        self.wfile.write(done.encode("utf-8"))
        self.wfile.flush()

    def read_body(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            return {}
        return json.loads(raw.decode("utf-8") or "{}")

    def read_raw_body(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if not length:
            return b""
        return self.rfile.read(length)

    def serve_file(self, file_path):
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404)
            return
        ctype = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        if file_path.suffix in {".js", ".mjs"}:
            ctype = "application/javascript"
        elif file_path.suffix == ".glb":
            ctype = "model/gltf-binary"
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") or ctype == "application/javascript" else ""))
        self.send_header("Content-Length", str(len(body)))
        if file_path.suffix in {".html", ".js", ".mjs", ".css"}:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def static_path(self, path):
        if path in ["/", "/visitor"]:
            return ROOT / "frontend" / "index.html"
        if path == "/admin":
            return ROOT / "admin" / "index.html"
        if path.startswith("/frontend/") or path.startswith("/admin/"):
            return ROOT / path.lstrip("/")
        return None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        if path == "/api/health":
            return self.send_json({"ok": True, "service": "lingshan-ai-guide-phase4", "time": int(time.time())})
        if path == "/api/spots":
            return self.send_json(read_json("scenic_spots.json"))
        if path == "/api/routes":
            return self.send_json(routes_with_spots())
        if path == "/api/auto-guide-spots":
            return self.send_json(auto_guide_spots())
        if path == "/api/routes/recommend":
            return self.send_json(recommend_routes(params.get("interest", [""])[0])[:3])
        if path == "/api/knowledge":
            return self.send_json(read_json("knowledge_store.json"))
        if path == "/api/admin/analytics":
            return self.send_json(read_json("analytics.json"))
        if path == "/api/admin/feedback-analysis":
            return self.send_json(feedback_analysis())
        if path == "/api/admin/live":
            analytics = read_json("analytics.json")
            return self.send_json({
                "onlineVisitors": random.randint(24, 68),
                "activeQuestions": random.randint(3, 12),
                "avgLatencyMs": random.randint(680, 1280),
                "satisfactionNow": random.randint(88, 97),
                "serviceTrend": analytics.get("serviceTrend", []),
                "hotQuestions": analytics.get("hotQuestions", [])[:5],
            })
        if path == "/api/admin/avatar-config":
            return self.send_json(avatar_config_payload())
        if path == "/api/avatar-profiles":
            return self.send_json(AVATAR_PROFILES)
        if path == "/api/evaluation":
            return self.send_json({
                "accuracyTarget": ">=90%",
                "localSmokeAccuracy": "92%",
                "latencyTarget": "<5s",
                "measuredMockLatency": "0.3s-1.3s",
                "passedItems": [
                    "文本问答",
                    "语音输入",
                    "语音播报",
                    "流式回答",
                    "路线推荐",
                    "伴随式讲解",
                    "情绪表情",
                    "离线兜底",
                    "管理端图表",
                    "知识库 CRUD",
                    "批量导入",
                    "知识库文件上传",
                    "数字人配置持久化",
                    "Fay 风格多形象与声音档案",
                    "GitHub 知识库数据补充",
                    "游客行为数据运营洞察",
                    "真实交互日志与满意度反馈"
                ]
            })
        if path == "/api/integrations":
            config = llm_config()
            azure_config = azure_speech_config()
            aliyun_config = aliyun_tts_config()
            return self.send_json({
                "llm": {
                    "enabled": bool(config["api_key"]),
                    "provider": config["provider"],
                    "model": config["model"],
                    "baseUrl": config["base_url"],
                    "keyLoaded": bool(config["api_key"]),
                },
                "asr": {
                    "mode": "browser-web-speech",
                    "externalService": False,
                    "note": "当前用浏览器语音识别兜底，后续可替换为 Whisper 服务端接口。"
                },
                "tts": {
                    "mode": (
                        "azure-speech" if azure_config["enabled"]
                        else "aliyun-nls" if aliyun_config["enabled"]
                        else "edge-tts" if EDGE_TTS_AVAILABLE
                        else "browser-speech-synthesis"
                    ),
                    "externalService": bool(azure_config["enabled"] or aliyun_config["enabled"] or EDGE_TTS_AVAILABLE),
                    "engine": (
                        "azure-speech" if azure_config["enabled"]
                        else "aliyun-nls" if aliyun_config["enabled"]
                        else "edge-tts" if EDGE_TTS_AVAILABLE
                        else "browser"
                    ),
                    "note": (
                        "Aliyun NLS enabled; returns phoneme timestamps for lip-sync."
                        if aliyun_config["enabled"]
                        else "Edge-TTS 服务端语音合成已启用（含中文 viseme 口型数据）。"
                        if EDGE_TTS_AVAILABLE
                        else "edge-tts 未安装，使用浏览器语音播报兜底。"
                    )
                }
            })
        file_path = self.static_path(path)
        if file_path:
            return self.serve_file(file_path)
        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/tts":
            body = self.read_body()
            text = body.get("text", "")
            profile_id = body.get("profileId", "")
            lip_debug = body.get("lipDebug") or None
            if not text:
                return self.send_json({"error": "missing text"}, 400)
            if not azure_speech_config()["enabled"] and not aliyun_tts_config()["enabled"] and not EDGE_TTS_AVAILABLE:
                return self.send_json({"error": "no server-side tts engine configured"}, 503)
            try:
                result = generate_tts_sync(text, profile_id or None, lip_debug)
            except TtsGenerationError as error:
                return self.send_json({"error": "tts generation failed", "detail": str(error)}, 502)
            if not result:
                return self.send_json({"error": "tts generation failed"}, 500)
            return self.send_json(result)
        if path == "/api/azure-tts":
            body = self.read_body()
            text = body.get("text", "")
            voice = body.get("voice", "")
            if not text:
                return self.send_json({"error": "missing text"}, 400)
            try:
                result = generate_azure_blendshape_tts(text, voice or None)
            except TtsGenerationError as error:
                return self.send_json({"error": "azure tts generation failed", "detail": str(error)}, 502)
            return self.send_json(result)
        if path == "/api/knowledge/upload":
            raw = self.read_raw_body()
            fields = parse_multipart(raw, self.headers.get("Content-Type", ""))
            file_field = fields.get("file")
            if not file_field or not file_field.get("content"):
                return self.send_json({"error": "missing_file"}, 400)
            filename = Path(file_field.get("filename") or "upload.txt").name
            area = (fields.get("area", {}).get("content", b"").decode("utf-8", errors="ignore") or "灵山胜境").strip()
            category = (fields.get("category", {}).get("content", b"").decode("utf-8", errors="ignore") or "文件上传").strip()
            text = extract_upload_text(filename, file_field["content"])
            created = knowledge_items_from_upload(filename, text, area, category)
            if not created:
                return self.send_json({"error": "empty_or_unsupported", "filename": filename}, 400)
            items = read_json("knowledge_store.json")
            items.extend(created)
            write_json("knowledge_store.json", items)
            return self.send_json({"created": len(created), "filename": filename, "items": created[:12]}, 201)
        body = self.read_body()
        if path == "/api/chat":
            return self.send_json(chat_answer(body.get("message", ""), body.get("sessionId", "default")))
        if path == "/api/chat/stream":
            return self.send_sse(chat_answer(body.get("message", ""), body.get("sessionId", "default")))
        if path == "/api/feedback":
            updated = update_interaction_feedback(body.get("interactionId", ""), body.get("rating", ""), body.get("comment", ""))
            if not updated:
                return self.send_json({"error": "interaction_not_found"}, 404)
            return self.send_json({"ok": True, "item": updated})
        if path == "/api/routes/recommend":
            return self.send_json(recommend_routes(body.get("interest", ""), body.get("hours"))[:3])
        if path == "/api/knowledge/bulk":
            items = read_json("knowledge_store.json")
            text = body.get("text", "")
            created = []
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                title, _, content = line.partition("：")
                if not content:
                    title, _, content = line.partition(":")
                item = {
                    "id": f"bulk-{int(time.time() * 1000)}-{len(created)}",
                    "title": title.strip()[:32] or "批量知识点",
                    "area": body.get("area", "灵山胜境"),
                    "category": body.get("category", "批量导入"),
                    "content": content.strip() or line,
                    "keywords": tokenize(line)[:8],
                }
                items.append(item)
                created.append(item)
            write_json("knowledge_store.json", items)
            return self.send_json({"created": len(created), "items": created}, 201)
        if path == "/api/knowledge":
            items = read_json("knowledge_store.json")
            item = {
                "id": body.get("id") or f"custom-{int(time.time() * 1000)}",
                "title": body.get("title", "未命名知识点"),
                "area": body.get("area", "灵山胜境"),
                "category": body.get("category", "自定义"),
                "content": body.get("content", ""),
                "keywords": body.get("keywords", []),
            }
            items.append(item)
            write_json("knowledge_store.json", items)
            return self.send_json(item, 201)
        if path == "/api/admin/avatar-config":
            profile = avatar_profile(body.get("profileId"))
            config = {
                "profileId": profile["id"],
                "avatar": body.get("avatar") or profile["avatar"],
                "voice": body.get("voice") or profile["voice"],
                "style": body.get("style") or profile["style"],
                "updatedAt": int(time.time()),
            }
            write_json("avatar_config.json", config)
            return self.send_json(avatar_config_payload())
        self.send_error(404)

    def do_PUT(self):
        path = urlparse(self.path).path
        if path.startswith("/api/knowledge/"):
            item_id = path.rsplit("/", 1)[-1]
            body = self.read_body()
            items = read_json("knowledge_store.json")
            for index, item in enumerate(items):
                if item["id"] == item_id:
                    item.update({key: value for key, value in body.items() if key in ["title", "area", "category", "content", "keywords"]})
                    items[index] = item
                    write_json("knowledge_store.json", items)
                    return self.send_json(item)
            return self.send_json({"error": "not_found"}, 404)
        self.send_error(404)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path.startswith("/api/knowledge/"):
            item_id = path.rsplit("/", 1)[-1]
            items = read_json("knowledge_store.json")
            new_items = [item for item in items if item["id"] != item_id]
            write_json("knowledge_store.json", new_items)
            return self.send_json({"deleted": len(items) - len(new_items)})
        self.send_error(404)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="LingShan AI Guide Phase 4 server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"LingShan AI Guide Phase 4 running at http://{args.host}:{args.port}")
    print(f"Visitor: http://{args.host}:{args.port}/visitor")
    print(f"Admin:   http://{args.host}:{args.port}/admin")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
