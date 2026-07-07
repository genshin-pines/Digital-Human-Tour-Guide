# 灵山胜境 AI 数字人导游 - 阶段 4 冲刺版

当前版本完成阶段 4 的加分项与体验打磨，目标是作为比赛初赛演示版：界面更像完整产品，游客端不再纵向撑屏，管理端具备实时大屏、登录、知识库导入和数字人配置。

## 启动

双击：

```text
E:\codex数字人\start.bat
```

启动后会分别打开两个 UI 窗口：

- 游客端：http://127.0.0.1:8000/visitor
- 管理后台：http://127.0.0.1:8000/admin
- 验收接口：http://127.0.0.1:8000/api/evaluation
- 外部服务状态：http://127.0.0.1:8000/api/integrations

管理后台演示账号：

```text
admin / 123456
```

## 阶段 4 已完成

### 游客端

- 屏幕适配优化：路线详情不再放在右侧长列表下方，改为中间主区域“问答 / 路线详情”切换。
- 本地 RAG 问答：已根据 `YQSY-HX/AI_Tour_Agent/backend/knowledge_base` 补充 22 个结构化景点、4 条路线、54 条知识文档。
- 流式回答：逐段显示，模拟大模型实时输出。
- 语音输入：浏览器 Web Speech API，Edge/Chrome 支持较好。
- 3D 数字人：游客端使用本地 Three.js 渲染景区风格数字人舞台，包含莲台、山水光环、讲解员服饰和角色配色，WebGL 不可用时自动回退到 CSS 立体头像。
- 手动语音播报：浏览器 SpeechSynthesis 朗读回答，已取消自动朗读，回答和路线讲解都由用户点击播放。
- 播放控制：语音播报支持播放、暂停、继续、停止，并对长文本做分段队列处理，减少浏览器朗读卡住。
- 口型动画：回答、播报、讲解时联动 3D 口型和点头动作。
- 情绪表情：平静、开心、好奇、着急状态渐变切换。
- 伴随式讲解：路线详情里逐景点讲解，并高亮当前讲解点。
- 离线兜底：最近路线缓存到 localStorage，接口异常时仍可查看。
- 追问建议：回答后给出可继续点击的问题。
- 置信度展示：游客端展示本次回答可信度。

### 管理后台

- 登录页：演示账号 admin / 123456。
- 实时大屏：在线游客、活跃咨询、平均延迟、即时满意率每 3 秒刷新。
- 静态图表：服务趋势、消费结构、满意度、客单价趋势。
- 知识库 CRUD：新增、修改、删除、查看。
- 批量导入：按“标题：内容”逐行导入知识点。
- 数字人配置持久化：形象、声音、风格保存到 `data/avatar_config.json`。
- Fay 风格形象档案：内置 5 套数字人形象与声音档案，包括灵山讲解员、拈花湾禅意讲解员、历史文化学者、亲子活力版、服务调度版；管理端保存后游客端会应用对应外观、标签、语速、音高和系统语音候选。
- 游客报告：满意度分布展示，并补充源数据记录数、游客行为样本和运营洞察。
- 真实反馈分析：游客每次问答会记录交互日志，游客端可点击满意/一般/不满意，管理端可查看热门问题、关键词、知识命中、路线兴趣、情绪趋势和运营建议。
- 知识库文件上传：管理端支持上传 `.txt`、`.md`、`.json`、`.docx`，自动拆分为可检索知识条目。

### 数据补充

- 新增导入脚本：`tools/import_github_knowledge.py`，可从 GitHub 知识库 txt 重新生成项目 JSON。
- 景点数据：导入灵山胜境 16 个节点、拈花湾 6 个节点，包含位置、建筑参数、文化内涵、亮点、开放信息和建议停留时长。
- 路线数据：新增“拈花湾禅意夜游线”，并强化拈花湾、夜游、休闲、灯光秀、禅意相关推荐。
- 行为数据：导入 777 条灵山相关记录摘要，补充停留、消费、满意度和长三角 TOP 景区统计字段。

## 后端接口

- `/api/chat`
- `/api/chat/stream`
- `/api/routes`
- `/api/routes/recommend`
- `/api/spots`
- `/api/knowledge`
- `/api/knowledge/bulk`
- `/api/knowledge/upload`
- `/api/feedback`
- `/api/admin/analytics`
- `/api/admin/feedback-analysis`
- `/api/admin/live`
- `/api/admin/avatar-config`
- `/api/avatar-profiles`
- `/api/evaluation`
- `/api/integrations`

## 接入真实大模型

当前已支持 OpenAI-compatible 的 DeepSeek / Qwen Chat Completions。配置后，系统流程会变成：

```text
用户问题 -> 本地资料检索 -> 拼接景区上下文 -> DeepSeek/Qwen 生成回答 -> 前端流式展示/语音播报
```

使用方式：

1. 复制 `.env.example` 为 `.env`
2. 填入你的 Key
3. 重新双击 `start.bat`

DeepSeek 示例：

```text
LINGSHAN_LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的DeepSeek Key
LINGSHAN_LLM_MODEL=deepseek-chat
LINGSHAN_LLM_BASE_URL=https://api.deepseek.com
```

Qwen 示例：

```text
LINGSHAN_LLM_PROVIDER=qwen
DASHSCOPE_API_KEY=你的DashScope Key
LINGSHAN_LLM_MODEL=qwen-plus
LINGSHAN_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

如果没有配置 Key，系统会自动回退到本地 RAG，不会影响运行。

## 说明

为了保持双击即用，当前没有强制安装外部依赖。真实大模型已支持配置接入；语音识别和 TTS 仍使用浏览器原生能力作为稳定兜底，后续可继续替换为 Whisper 和 Edge-TTS 服务端接口。
