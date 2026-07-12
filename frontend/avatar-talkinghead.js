import { TalkingHead } from "./talkinghead/talkinghead.mjs";

const shell = document.querySelector("#avatar");
const stage = document.querySelector("#talkingHeadAvatar");
const loading = document.querySelector("#avatarLoading");

const MOOD_BY_STATE = {
  normal: "neutral",
  smile: "happy",
  thinking: "neutral",
  focused: "neutral",
  listening: "neutral",
  speaking: "happy",
};

const MOOD_BY_EMOTION = {
  平静: "neutral",
  认真: "neutral",
  思考: "neutral",
  开心: "happy",
  高兴: "happy",
  欢迎: "happy",
  赞许: "happy",
  紧张: "fear",
  抱歉: "sad",
  遗憾: "sad",
};

const AZURE_MOUTH_GAIN = 0.85;
const AZURE_MOUTH_TARGETS = new Set([
  "jawForward", "jawLeft", "jawRight", "jawOpen", "mouthClose",
  "mouthFunnel", "mouthPucker", "mouthLeft", "mouthRight",
  "mouthSmileLeft", "mouthSmileRight", "mouthFrownLeft", "mouthFrownRight",
  "mouthDimpleLeft", "mouthDimpleRight", "mouthStretchLeft", "mouthStretchRight",
  "mouthRollLower", "mouthRollUpper", "mouthShrugLower", "mouthShrugUpper",
  "mouthPressLeft", "mouthPressRight", "mouthLowerDownLeft", "mouthLowerDownRight",
  "mouthUpperUpLeft", "mouthUpperUpRight", "tongueOut",
]);

let head = null;
let ready = false;
let readyPromise = null;
let currentMood = "neutral";
let queuedText = "";
let speakTimer = 0;
let availableMorphs = new Set();
let lastServerAudio = null;
let lastAzureStats = null;

function setLoading(text) {
  if (loading) loading.textContent = text;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function clearSpeakTimer() {
  if (speakTimer) window.clearTimeout(speakTimer);
  speakTimer = 0;
}

function refreshMorphTargets() {
  try {
    availableMorphs = new Set(head?.getMorphTargetNames?.() || []);
  } catch {
    availableMorphs = new Set();
  }
}

function hasMorph(name) {
  return !availableMorphs.size || availableMorphs.has(name);
}

function setMorph(name, value, ms = 80) {
  if (!head || !name || !hasMorph(name)) return false;
  try {
    head.setValue(name, value, ms);
    return true;
  } catch {
    return false;
  }
}

function resetAzureMouthTargets(ms = 120) {
  for (const name of AZURE_MOUTH_TARGETS) setMorph(name, 0, ms);
  for (const name of ["mouthOpen", "jawOpen"]) setMorph(name, 0, ms);
}

function bytesFromBase64(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function scaleAzureBlendshape(name, value, gain = AZURE_MOUTH_GAIN) {
  const numeric = Number(value || 0);
  if (!AZURE_MOUTH_TARGETS.has(name)) return numeric;
  if (name === "mouthClose") return numeric;
  const extraJaw = name === "jawOpen" ? 0.92 : 1;
  const cap = name === "jawOpen" ? 0.72 : 0.9;
  return clamp(numeric * gain * extraJaw, 0, cap);
}

function buildAzureBlendshapeAnim(payload, gain = AZURE_MOUTH_GAIN) {
  const names = payload?.blendshapeNames || [];
  const frames = payload?.blendshapeFrames || [];
  const frameRate = Number(payload?.frameRate || 60);
  const vs = {};
  let usedTargets = 0;

  names.forEach((name, index) => {
    if (!hasMorph(name)) return;
    const values = frames.map((frame) => scaleAzureBlendshape(name, frame?.[index], gain));
    values.unshift(0);
    vs[name] = values;
    usedTargets += 1;
  });

  return {
    name: "blendshapes",
    dt: Array.from({ length: frames.length }, () => 1000 / frameRate),
    vs,
    durationMs: frames.length * (1000 / frameRate),
    usedTargets,
  };
}

function applyMood(mood) {
  if (!ready || !head || !mood) return;
  try {
    head.setMood(mood);
    currentMood = mood;
  } catch {
    try {
      head.setMood("neutral");
      currentMood = "neutral";
    } catch {}
  }
}

async function waitUntilReady(timeoutMs = 6000) {
  if (ready && head) return true;
  if (!readyPromise) return false;
  const timeout = new Promise((resolve) => window.setTimeout(() => resolve(false), timeoutMs));
  await Promise.race([readyPromise.then(() => true).catch(() => false), timeout]);
  return Boolean(ready && head);
}

function estimateSpeechMs(text) {
  const chineseChars = (String(text || "").match(/[\u4e00-\u9fff]/g) || []).length;
  const otherChars = String(text || "").replace(/[\u4e00-\u9fff\s]/g, "").length;
  return clamp(chineseChars * 230 + otherChars * 75 + 700, 900, 24000);
}

async function init() {
  if (!shell || !stage) return;
  shell.classList.add("talkinghead-shell");
  setLoading("正在加载 3D 数字人...");

  readyPromise = (async () => {
    head = new TalkingHead(stage, {
      cameraView: "upper",
      lipsyncModules: ["en"],
    });

    await head.showAvatar({
      url: "/frontend/talkinghead/guide.glb",
      body: "F",
      avatarMood: "neutral",
      lipsyncLang: "en",
    }, (ev) => {
      if (ev?.lengthComputable && ev.total) {
        setLoading(`正在加载 3D 数字人 ${Math.min(100, Math.round((ev.loaded / ev.total) * 100))}%`);
      }
    });

    refreshMorphTargets();
    ready = true;
    shell.classList.add("talkinghead-ready");
    shell.classList.remove("talkinghead-error");
    setLoading("3D 数字人已就绪");
    applyMood(currentMood);

    if (queuedText) {
      const text = queuedText;
      queuedText = "";
      window.lingshanAvatar.speakText(text);
    }
  })();

  try {
    await readyPromise;
  } catch (error) {
    console.error("TalkingHead init failed", error);
    shell.classList.add("talkinghead-error");
    setLoading("3D 数字人加载失败，请检查模型资源");
  }
}

window.lingshanAvatar = {
  speakText(text, options = {}) {
    queuedText = String(text || "");
    if (options.mood) applyMood(options.mood);
    if (!queuedText || !ready || !head) return;

    clearSpeakTimer();
    try {
      head.stopSpeaking();
      head.lookAtCamera?.(350);
      head.speakText?.(queuedText, { avatarMute: true, avatarMood: currentMood });
      shell?.classList.add("speaking");
      speakTimer = window.setTimeout(() => {
        shell?.classList.remove("speaking");
        resetAzureMouthTargets(120);
      }, estimateSpeechMs(queuedText));
    } catch (error) {
      console.warn("TalkingHead speakText fallback failed", error);
    }
  },

  async speakWithBlendshapes(audioData, payload, options = {}) {
    const isReady = await waitUntilReady();
    if (!isReady) return false;
    if (!audioData || !payload?.blendshapeFrames?.length || !payload?.blendshapeNames?.length) return false;

    try {
      clearSpeakTimer();
      head.stopSpeaking();
      head.lookAtCamera?.(350);
      resetAzureMouthTargets(40);

      const audioBytes = bytesFromBase64(audioData);
      const audioBuffer = await head.audioCtx.decodeAudioData(audioBytes.buffer.slice(0));
      const anim = buildAzureBlendshapeAnim(payload, Number(options.mouthGain || AZURE_MOUTH_GAIN));
      if (!Object.keys(anim.vs).length) {
        console.warn("[lip:azure] no matching ARKit morph targets on current GLB");
        return false;
      }

      lastServerAudio = audioBuffer;
      lastAzureStats = {
        provider: payload.provider,
        source: payload.lipsyncSource,
        frameRate: payload.frameRate,
        frames: payload.blendshapeFrames.length,
        azureShapeNames: payload.blendshapeNames.length,
        matchedMorphTargets: anim.usedTargets,
        gain: Number(options.mouthGain || AZURE_MOUTH_GAIN),
      };

      head.speakAudio({
        audio: audioBuffer,
        anim: {
          name: anim.name,
          dt: anim.dt,
          vs: anim.vs,
        },
      }, {}, null);

      console.log("[lip:azure]", lastAzureStats);
      shell?.classList.add("speaking");
      speakTimer = window.setTimeout(() => {
        shell?.classList.remove("speaking");
        resetAzureMouthTargets(140);
      }, anim.durationMs + 700);

      return true;
    } catch (error) {
      console.warn("TalkingHead speakWithBlendshapes failed", error);
      return false;
    }
  },

  speakWithTimeline() {
    // Kept only for old Aliyun fallback. If Azure is configured, the main path
    // should always use speakWithBlendshapes, matching the verified demo page.
    return false;
  },

  stopSpeaking() {
    clearSpeakTimer();
    queuedText = "";
    shell?.classList.remove("speaking");
    resetAzureMouthTargets(120);
    try { head?.stopSpeaking(); } catch {}
  },

  pauseSpeaking() {
    try { head?.pauseSpeaking?.(); } catch {}
    shell?.classList.remove("speaking");
  },

  resumeSpeaking() {
    try { head?.startSpeaking?.(); } catch {}
    shell?.classList.add("speaking");
  },

  getServerTtsAudio() { return null; },
  getEdgeTtsAudio() { return null; },
  getServerTtsPlaying() { return false; },
  getEdgeTtsPlaying() { return false; },

  getLipSyncDebugInfo() {
    return {
      ready,
      morphTargets: [...availableMorphs].sort(),
      activeAudio: Boolean(lastServerAudio),
      azure: lastAzureStats,
    };
  },

  syncSpeechBoundary() {
    // Browser speech fallback is no longer the quality path.
  },

  setMood(stateOrMood, emotionName = "") {
    const mood = MOOD_BY_EMOTION[emotionName] || MOOD_BY_STATE[stateOrMood] || stateOrMood || "neutral";
    currentMood = mood;
    applyMood(mood);
  },

  setListening(active) {
    shell?.classList.toggle("listening", Boolean(active));
    if (active) applyMood("neutral");
  },

  start() {
    try { head?.start(); } catch {}
  },

  stop() {
    try { head?.stop(); } catch {}
  },

  previewVisemes(moValue = 0.7) {
    if (!ready || !head) return false;
    this.stopSpeaking();
    const targets = [...AZURE_MOUTH_TARGETS].filter((name) => hasMorph(name));
    if (!targets.length) return false;
    let index = 0;
    let frameId = 0;
    let lastSwitch = 0;

    const tick = (now) => {
      if (!lastSwitch) lastSwitch = now;
      const target = targets[index];
      resetAzureMouthTargets(40);
      setMorph(target, target === "jawOpen" ? moValue * 0.72 : moValue, 40);
      if (now - lastSwitch >= 850) {
        lastSwitch = now;
        index = (index + 1) % targets.length;
      }
      frameId = requestAnimationFrame(tick);
    };

    frameId = requestAnimationFrame(tick);
    window.setTimeout(() => {
      cancelAnimationFrame(frameId);
      resetAzureMouthTargets(120);
    }, Math.max(1200, targets.length * 850));
    return true;
  },
};

init();

document.addEventListener("visibilitychange", () => {
  if (!head) return;
  if (document.visibilityState === "visible") window.lingshanAvatar.start();
  else window.lingshanAvatar.stop();
});
