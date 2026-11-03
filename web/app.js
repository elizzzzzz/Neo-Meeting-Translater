const inputDevice = document.querySelector('#inputDevice');
const sourceLanguage = document.querySelector('#sourceLanguage');
const targetLanguage = document.querySelector('#targetLanguage');
const speakerMode = document.querySelector('#speakerMode');
const startBtn = document.querySelector('#startBtn');
const stopBtn = document.querySelector('#stopBtn');
const swapLanguagesBtn = document.querySelector('#swapLanguages');
const exportBtn = document.querySelector('#exportBtn');
const clearBtn = document.querySelector('#clearBtn');
const floatingBtn = document.querySelector('#floatingBtn');
const demoBtn = document.querySelector('#demoBtn');
const tipsBtn = document.querySelector('#tipsBtn');
const settingsBtn = document.querySelector('#settingsBtn');
const tipsModal = document.querySelector('#tipsModal');
const settingsModal = document.querySelector('#settingsModal');
const closeTipsBtn = document.querySelector('#closeTipsBtn');
const continueTipsBtn = document.querySelector('#continueTipsBtn');
const closeSettingsBtn = document.querySelector('#closeSettingsBtn');
const rememberTips = document.querySelector('#rememberTips');
const ollamaInstallStatus = document.querySelector('#ollamaInstallStatus');
const ollamaVersionStatus = document.querySelector('#ollamaVersionStatus');
const recommendedModelStatus = document.querySelector('#recommendedModelStatus');
const recommendedModelPresence = document.querySelector('#recommendedModelPresence');
const systemNotice = document.querySelector('#systemNotice');
const modelDirectory = document.querySelector('#modelDirectory');
const chooseModelDirectoryBtn = document.querySelector('#chooseModelDirectoryBtn');
const checkOllamaBtn = document.querySelector('#checkOllamaBtn');
const upgradeOllamaBtn = document.querySelector('#upgradeOllamaBtn');
const pullModelBtn = document.querySelector('#pullModelBtn');
const saveSettingsBtn = document.querySelector('#saveSettingsBtn');
const captions = document.querySelector('#captions');
const captionCount = document.querySelector('#captionCount');
const runtimeDot = document.querySelector('#runtimeDot');
const runtimeText = document.querySelector('#runtimeText');
const modelReadiness = document.querySelector('#modelReadiness');
const sessionLabel = document.querySelector('#sessionLabel');
const sourceStatus = document.querySelector('#sourceStatus');
const directionStatus = document.querySelector('#directionStatus');
const speakerStatus = document.querySelector('#speakerStatus');
const modeStatus = document.querySelector('#modeStatus');
const modeBadge = document.querySelector('#modeBadge');
const asrStatus = document.querySelector('#asrStatus');
const ollamaStatus = document.querySelector('#ollamaStatus');
const ollamaModelStatus = document.querySelector('#ollamaModelStatus');
const translationStatus = document.querySelector('#translationStatus');
const audioStatus = document.querySelector('#audioStatus');
const diagnosticStatus = document.querySelector('#diagnosticStatus');
const directionPill = document.querySelector('#directionPill');
const serviceAddress = document.querySelector('#serviceAddress');
const directionButtons = [...document.querySelectorAll('.direction-button')];

let socket;
let audioContext;
let mediaStream;
let processor;
let captionRows = [];
let runtimeMode = 'MOCK';
const mockCaptionKeys = new Set();
const VOICE_RMS_THRESHOLD = 0.02;
const VOICE_PEAK_THRESHOLD = 0.08;
const CALIBRATION_FRAMES = 4;
let noiseSamples = [];
let noiseFloorRms = VOICE_RMS_THRESHOLD;
let noiseFloorPeak = VOICE_PEAK_THRESHOLD;
let voiceHits = 0;
let audioFrames = 0;
let lastCaptionAt = 0;
let sessionStartedAt = 0;
let floatingMode = false;
let modelsReady = false;
let demoTimer;
let demoStep = 0;
let demoSession = "";

function setDiagnostic(message) {
  diagnosticStatus.textContent = message;
  sessionLabel.textContent = message;
}
function formatModel(value) {
  const text = String(value || '未配置');
  return text.length > 28 ? `${text.slice(0, 25)}…` : text;
}
function statusText(value) {
  return ({ loading: '加载中', ready: '已就绪', running: '运行中', processing: '推理中', configured: '已配置', offline: '未连接', missing: '缺少模型', error: '错误', mock: '演示' })[String(value || '').toLowerCase()] || String(value || '未知');
}
function updateHealth(health) {
  runtimeMode = String(health.mode || 'mock').toUpperCase();
  const modeLabel = runtimeMode === 'LOCAL' ? '本地' : '演示';
  modeStatus.textContent = modeLabel;
  modeBadge.textContent = modeLabel;
  const models = health.models || {};
  if (modelReadiness) {
    modelsReady = Boolean(models.ready);
    modelReadiness.textContent = runtimeMode === 'MOCK' ? '界面演示 · 不使用真实模型' : models.ready ? '模型可用 · 热启动' : `${Math.round(Number(models.progress || 0))}% · ${models.message || '模型未就绪'}`;
    modelReadiness.classList.toggle('ready', Boolean(models.ready));
    modelReadiness.classList.toggle('error', models.stage === 'error');
  }
  startBtn.disabled = runtimeMode !== 'LOCAL' || !models.ready || Boolean(socket && socket.readyState <= WebSocket.OPEN) || Boolean(demoTimer);
  startBtn.title = runtimeMode !== 'LOCAL' ? '尚未连接真实模型，可先演示字幕和浮窗' : !models.ready ? '模型未就绪，请先检查本地设置' : '';
  if (runtimeMode === 'LOCAL' && !models.ready && !demoTimer) setDiagnostic(models.message || '模型未连接，可先演示字幕');
  asrStatus.textContent = `${statusText(health.asr?.status)} · ${formatModel(health.asr?.model)}`;
  if (!health.ollama?.configured) {
    ollamaStatus.textContent = '未启用';
    ollamaModelStatus.textContent = '当前使用其他翻译后端';
  } else if (!health.ollama.reachable) {
    ollamaStatus.textContent = '未启动 / 无法连接';
    ollamaModelStatus.textContent = formatModel(health.translation?.model);
  } else if (!health.ollama.model_present) {
    ollamaStatus.textContent = '已启动';
    ollamaModelStatus.textContent = `缺少模型 · ${formatModel(health.translation?.model)}`;
  } else if (health.translation?.status === 'processing') {
    ollamaStatus.textContent = '已启动 · 模型推理中';
    ollamaModelStatus.textContent = `推理中 · ${formatModel(health.translation?.model)}`;
  } else if (health.ollama.model_loaded) {
    ollamaStatus.textContent = '已启动 · 模型运行中';
    ollamaModelStatus.textContent = `运行中 · ${formatModel(health.translation?.model)}`;
  } else {
    ollamaStatus.textContent = '已启动 · 等待调用';
    ollamaModelStatus.textContent = `已安装，尚未加载 · ${formatModel(health.translation?.model)}`;
  }
  const responseMs = health.translation?.last_response_ms ? ` · 最近响应 ${health.translation.last_response_ms} ms` : '';
  translationStatus.textContent = `${statusText(health.translation?.status)}${responseMs}`;
  const frames = Number(health.audio?.frames || 0);
  if (frames > audioFrames) audioStatus.textContent = `已收到 ${frames} 帧`;
  if (health.last_error) diagnosticStatus.textContent = health.last_error;
  document.querySelectorAll('.status-list dd').forEach(value => { value.title = value.textContent; });
}

function toggleModal(modal, visible) {
  if (!modal) return;
  modal.hidden = !visible;
  if (visible) modal.querySelector('button, input')?.focus();
}
async function closeTips() {
  try {
    const response = await fetch('/preferences', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ show_tips: !rememberTips.checked }),
    });
    if (!response.ok) throw new Error('偏好保存失败');
    toggleModal(tipsModal, false);
    return true;
  } catch {
    setDiagnostic('无法保存使用提示设置，请稍后重试');
    return false;
  }
}
async function loadPreferences() {
  try {
    const response = await fetch('/preferences');
    if (!response.ok) throw new Error('无法读取偏好');
    const settings = await response.json();
    rememberTips.checked = settings.show_tips === false;
    toggleModal(tipsModal, settings.show_tips !== false);
  } catch { toggleModal(tipsModal, true); }
}
async function openSettings() {
  toggleModal(settingsModal, true);
  try {
    const response = await fetch('/settings');
    const settings = await response.json();
    if (!modelDirectory.value) modelDirectory.value = settings.model_dir || '';
  } catch { setDiagnostic('无法读取本地设置'); }
  await checkOllama();
}
function describeSystem(info) {
  if (!info.installed) return '尚未检测到 Ollama。安装后可使用本地翻译引擎。';
  if (info.update_available) return `发现 Ollama 新版本 ${info.latest_version}，可点击“尝试升级 Ollama”。`;
  if (!info.reachable) return '已检测到 Ollama，但服务尚未运行。打开 Ollama 后点击重新检查。';
  if (!info.recommended_model_present) return `Ollama 已运行，推荐模型 ${info.recommended_model} 尚未下载。`;
  return `Ollama 已安装并运行，推荐模型 ${info.recommended_model} 可用。`;
}
async function checkOllama() {
  if (systemNotice) { systemNotice.className = 'system-notice'; systemNotice.textContent = '正在检查 Ollama 和推荐模型…'; }
  try {
    const response = await fetch('/system/check');
    const info = await response.json();
    const recommended = info.recommended_model || 'translategemma:4b';
    ollamaInstallStatus.textContent = info.installed ? (info.reachable ? '已安装并运行' : '已安装，服务未运行') : '未安装';
    ollamaVersionStatus.textContent = info.version ? `${info.version} · ${info.version_check || '待核对'}` : '未检测到版本';
    recommendedModelStatus.textContent = recommended;
    recommendedModelPresence.textContent = info.recommended_model_present ? '已下载，可直接使用' : '尚未下载';
    if (systemNotice) {
      systemNotice.textContent = describeSystem(info);
      systemNotice.className = `system-notice ${info.installed && info.recommended_model_present && !info.update_available ? 'good' : 'warn'}`;
    }
    upgradeOllamaBtn.disabled = !info.installed || !info.brew_available;
    pullModelBtn.disabled = !info.installed || !info.reachable || Boolean(info.recommended_model_present);
    pullModelBtn.textContent = info.recommended_model_present ? '推荐模型已就绪' : '安装推荐模型';
  } catch (error) {
    if (systemNotice) { systemNotice.className = 'system-notice warn'; systemNotice.textContent = `检测失败：${error.message || '本地服务不可用'}`; }
  }
}
async function saveModelDirectory() {
  const value = modelDirectory?.value?.trim();
  if (!value) return;
  saveSettingsBtn.disabled = true;
  try {
    const response = await fetch('/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model_dir: value }) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || '保存失败');
    setDiagnostic('模型目录已保存，重新打开 App 后生效');
    if (systemNotice) { systemNotice.className = 'system-notice good'; systemNotice.textContent = `已保存：${result.model_dir}。重新打开 App 后加载新目录。`; }
  } catch (error) {
    if (systemNotice) { systemNotice.className = 'system-notice warn'; systemNotice.textContent = `保存失败：${error.message}`; }
  } finally { saveSettingsBtn.disabled = false; }
}
window.__onModelDirectorySelected = (path) => { if (modelDirectory) modelDirectory.value = path; };

function resetVoiceDetection() {
  noiseSamples = [];
  noiseFloorRms = VOICE_RMS_THRESHOLD;
  noiseFloorPeak = VOICE_PEAK_THRESHOLD;
  voiceHits = 0;
}

function setRuntime(active, text) { runtimeDot.classList.toggle('active', active); runtimeText.textContent = text; }
function setFloatingMode(enabled) {
  floatingMode = enabled;
  document.body.classList.toggle('floating-mode', enabled);
  if (floatingBtn) floatingBtn.textContent = enabled ? '退出浮窗' : '字幕浮窗';
  if (window.webkit?.messageHandlers?.native) {
    window.webkit.messageHandlers.native.postMessage({ type: 'floating', enabled });
  }
}
function updateSummary() {
  captionCount.textContent = String(captionRows.length);
  const sourceLabel = sourceLanguage.options[sourceLanguage.selectedIndex]?.textContent || '自动识别';
  const targetLabel = targetLanguage.options[targetLanguage.selectedIndex]?.textContent || '中文（简体）';
  const direction = `${sourceLabel} → ${targetLabel}`;
  directionStatus.textContent = direction;
  directionPill.textContent = direction;
  speakerStatus.textContent = speakerMode.options[speakerMode.selectedIndex]?.textContent || '稍后区分';
  sourceStatus.textContent = inputDevice.options[inputDevice.selectedIndex]?.textContent || '未选择';
  directionButtons.forEach((button) => button.classList.toggle('selected', button.dataset.source === sourceLanguage.value && button.dataset.target === targetLanguage.value));
}
function ensureDifferentLanguages(changed) {
  if (sourceLanguage.value === 'auto' || sourceLanguage.value !== targetLanguage.value) return;
  if (changed === 'source') targetLanguage.value = sourceLanguage.value === 'zh' ? 'ja' : 'zh';
  else sourceLanguage.value = targetLanguage.value === 'zh' ? 'ja' : 'zh';
}
function setDirection(source, target) { sourceLanguage.value = source; targetLanguage.value = target; updateSummary(); }
function swapLanguages() {
  if (sourceLanguage.value === 'auto') sourceLanguage.value = targetLanguage.value === 'zh' ? 'ja' : 'zh';
  else [sourceLanguage.value, targetLanguage.value] = [targetLanguage.value, sourceLanguage.value];
  updateSummary();
}
function formatTime(milliseconds) { const totalSeconds = Math.max(0, Math.round(milliseconds / 1000)); return `${String(Math.floor(totalSeconds / 60)).padStart(2, '0')}:${String(totalSeconds % 60).padStart(2, '0')}`; }
function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character])); }
function renderCaptions() {
  if (!captionRows.length) { captions.innerHTML = '<div class="empty-state"><strong>还没有字幕</strong><span>选择麦克风或 BlackHole 回环设备后开始会议。</span></div>'; return; }
  captions.innerHTML = captionRows.map((event) => `<div class="caption-row"><span class="caption-time">${formatTime(event.start_ms)}</span><span><span class="speaker-chip">${escapeHtml(event.speaker_id)}</span></span><span class="caption-copy">${escapeHtml(event.original_text)}${event.is_final ? '' : '<span class="draft">临时</span>'}</span><span class="caption-copy caption-translation">${escapeHtml(event.translated_text || '翻译处理中…')}</span></div>`).join('');
  captions.scrollTop = captions.scrollHeight;
}
function downsample(buffer, inputRate, outputRate) {
  if (outputRate === inputRate) return buffer;
  const ratio = inputRate / outputRate; const length = Math.round(buffer.length / ratio); const result = new Float32Array(length);
  for (let index = 0; index < length; index += 1) result[index] = buffer[Math.min(Math.floor(index * ratio), buffer.length - 1)];
  return result;
}
function encodePcm(buffer) {
  const pcm = new Int16Array(buffer.length);
  for (let index = 0; index < buffer.length; index += 1) { const sample = Math.max(-1, Math.min(1, buffer[index])); pcm[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff; }
  const bytes = new Uint8Array(pcm.buffer); let binary = ''; for (const byte of bytes) binary += String.fromCharCode(byte); return btoa(binary);
}
function containsVoice(buffer) {
  if (!buffer.length) return false;
  let sumSquares = 0; let peak = 0;
  for (const sample of buffer) { const magnitude = Math.abs(sample); sumSquares += magnitude * magnitude; peak = Math.max(peak, magnitude); }
  const rms = Math.sqrt(sumSquares / buffer.length);
  if (noiseSamples.length < CALIBRATION_FRAMES) {
    noiseSamples.push({ rms, peak });
    if (noiseSamples.length === CALIBRATION_FRAMES) {
      const rmsValues = noiseSamples.map((sample) => sample.rms).sort((a, b) => a - b);
      const peakValues = noiseSamples.map((sample) => sample.peak).sort((a, b) => a - b);
      const midpoint = Math.floor(noiseSamples.length / 2);
      noiseFloorRms = Math.max(VOICE_RMS_THRESHOLD * 0.75, rmsValues[midpoint]);
      noiseFloorPeak = Math.max(VOICE_PEAK_THRESHOLD * 0.75, peakValues[midpoint]);
    }
    return false;
  }
  const candidate = rms >= Math.max(VOICE_RMS_THRESHOLD, noiseFloorRms * 2.0)
    && peak >= Math.max(VOICE_PEAK_THRESHOLD, noiseFloorPeak * 1.8);
  voiceHits = candidate ? voiceHits + 1 : 0;
  return voiceHits >= 2;
}
async function loadDevices() {
  if (!navigator.mediaDevices?.enumerateDevices) {
    inputDevice.innerHTML = '<option value="">默认麦克风（授权后显示名称）</option>';
    updateSummary(); return;
  }
  try {
    const devices = await navigator.mediaDevices.enumerateDevices(); const inputs = devices.filter((device) => device.kind === 'audioinput');
    inputDevice.innerHTML = inputs.length ? inputs.map((device, index) => `<option value="${escapeHtml(device.deviceId)}">${escapeHtml(device.label || `音频输入 ${index + 1}`)}</option>`).join('') : '<option value="">默认音频输入</option>';
    updateSummary();
  } catch { inputDevice.innerHTML = '<option value="">默认音频输入</option>'; sourceStatus.textContent = '设备读取失败'; }
}
async function startSession() {
  if (runtimeMode !== 'LOCAL' || !modelsReady || (socket && socket.readyState <= WebSocket.OPEN)) return;
  stopDemo(); lastCaptionAt = 0;
  startBtn.disabled = true; setRuntime(false, '连接中…');
  resetVoiceDetection();
  audioFrames = 0; audioStatus.textContent = '连接中…'; setDiagnostic('正在连接本地服务');
  sessionStartedAt = Date.now();
  if (!navigator.mediaDevices?.getUserMedia) {
    sessionLabel.textContent = '当前 App 不支持麦克风输入，请检查 macOS 麦克风权限。';
    startBtn.disabled = false;
    setRuntime(false, '不可用');
    return;
  }
  socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  socket.onopen = async () => {
    try {
      socket.send(JSON.stringify({ type: 'config', source_language: sourceLanguage.value, target_language: targetLanguage.value, speaker_mode: speakerMode.value }));
      const audio = { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true };
      if (inputDevice.value) audio.deviceId = { exact: inputDevice.value };
      try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio });
      } catch (error) {
        // Device IDs can change when macOS grants microphone permission. Retry
        // with the default input instead of ending the whole session.
        if (error.name !== 'OverconstrainedError' && error.name !== 'NotFoundError') throw error;
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      }
      audioContext = new AudioContext(); const source = audioContext.createMediaStreamSource(mediaStream); processor = audioContext.createScriptProcessor(4096, 1, 1);
      await audioContext.resume();
      processor.onaudioprocess = (event) => {
        if (socket.readyState !== WebSocket.OPEN) return;
        audioFrames += 1;
        if (audioFrames === 1 || audioFrames % 20 === 0) {
          audioStatus.textContent = `已发送 ${audioFrames} 帧`;
          if (!lastCaptionAt) setDiagnostic('已收到音频，正在等待语音识别');
        }
        const pcm = downsample(event.inputBuffer.getChannelData(0), audioContext.sampleRate, 16000);
        // Send every short PCM frame and let the server apply the mode-specific
        // silence gate. Browser-side VAD can mistake quiet speech for noise,
        // especially during the first frames after microphone permission.
        const label = inputDevice.options[inputDevice.selectedIndex]?.textContent || '';
        const sourceType = /blackhole|loopback|virtual/i.test(label) ? 'meeting_loopback' : 'microphone';
        socket.send(JSON.stringify({ type: 'audio', session_id: sourceType, audio_base64: encodePcm(pcm), sample_rate: 16000, channels: 1, source: sourceType }));
      };
      const silentOutput = audioContext.createGain(); silentOutput.gain.value = 0;
      source.connect(processor); processor.connect(silentOutput); silentOutput.connect(audioContext.destination); stopBtn.disabled = false; setDiagnostic(`音频已开启：${sourceStatus.textContent}`); setRuntime(true, '运行中');
    } catch (error) { cleanupAudio(); audioStatus.textContent = '失败'; setDiagnostic(`音频输入失败：${error.message || '请检查系统麦克风权限'}`); if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) socket.close(); }
  };
  socket.onmessage = (message) => {
    const event = JSON.parse(message.data);
    if (event.type === 'caption') {
      const captionKey = `${event.original_text || ''}\u0000${event.translated_text || ''}`;
      if (runtimeMode === 'MOCK' && mockCaptionKeys.has(captionKey)) return;
      if (runtimeMode === 'MOCK') mockCaptionKeys.add(captionKey);
      const existingIndex = captionRows.findIndex((row) => row.session_id === event.session_id && row.segment_id === event.segment_id);
      if (existingIndex >= 0) captionRows[existingIndex] = event;
      else captionRows.push(event);
      lastCaptionAt = Date.now();
      setDiagnostic(event.is_final ? '已识别并翻译字幕' : '已识别原文，翻译处理中');
      renderCaptions(); updateSummary();
    }
    if (event.type === 'status') setDiagnostic(event.message);
    if (event.type === 'error') setDiagnostic(`错误：${event.message}`);
  };
  socket.onclose = () => { cleanupAudio(); startBtn.disabled = runtimeMode !== 'LOCAL' || !modelsReady; stopBtn.disabled = true; setRuntime(false, '已停止'); };
  socket.onerror = () => { setDiagnostic('本地服务连接失败'); setRuntime(false, '连接失败'); };
}
function cleanupAudio() { if (processor) processor.disconnect(); if (audioContext) audioContext.close(); if (mediaStream) mediaStream.getTracks().forEach((track) => track.stop()); processor = null; audioContext = null; mediaStream = null; }
function stopSession() { stopDemo(); if (socket && socket.readyState <= WebSocket.OPEN) socket.close(); else cleanupAudio(); }
function exportTranscript() {
  const text = captionRows.map(row => `[${formatTime(row.start_ms)}] ${row.speaker_id}\n${row.original_text}\n${row.translated_text || ''}`).join('\n\n') || '暂无字幕';
  const filename = `meeting-${new Date().toISOString().slice(0, 10)}.txt`;
  if (window.webkit?.messageHandlers?.native) {
    window.webkit.messageHandlers.native.postMessage({ type: 'export_transcript', filename, text });
    return;
  }
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob); link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}
window.__onTranscriptExported = result => { setDiagnostic(result.message); };


const demoText = [
  { zh: '今天我们先确认会议议程。', ja: '今日はまず会議の議題を確認します。', en: "Let's confirm the meeting agenda first." },
  { zh: '请在周五之前发送更新后的方案。', ja: '金曜日までに更新した提案を送ってください。', en: 'Please send the updated proposal before Friday.' },
  { zh: '收到，我们会整理意见后再回复。', ja: '承知しました。意見をまとめてから返信します。', en: 'Understood. We will respond after collecting feedback.' },
];
function advanceDemo() {
  const index = Math.floor(demoStep / 2);
  if (index >= demoText.length) { stopDemo(); setDiagnostic('字幕演示完成 · 示例文字并非真实识别结果'); return; }
  const final = demoStep % 2 === 1;
  const source = sourceLanguage.value === 'auto' ? (targetLanguage.value === 'zh' ? 'ja' : 'zh') : sourceLanguage.value;
  const text = demoText[index];
  const event = {
    type: 'caption', session_id: demoSession, segment_id: `demo-${index}`,
    speaker_id: `示例发言人 ${index % 2 + 1}`, start_ms: index * 4000, end_ms: (index + 1) * 4000,
    original_text: final ? text[source] : text[source].slice(0, Math.max(3, Math.floor(text[source].length * .55))),
    translated_text: final ? text[targetLanguage.value] : '', is_final: final,
  };
  const existing = captionRows.findIndex(row => row.session_id === demoSession && row.segment_id === event.segment_id);
  if (existing >= 0) captionRows[existing] = event; else captionRows.push(event);
  demoStep += 1;
  renderCaptions(); updateSummary();
  setDiagnostic('示例字幕演示 · 可打开浮窗、移动窗口或导出记录');
}
function startDemo() {
  if (socket && socket.readyState <= WebSocket.OPEN) return;
  stopDemo(); demoStep = 0; demoSession = `demo-${Date.now()}`;
  demoTimer = setInterval(advanceDemo, 1600);
  stopBtn.disabled = false; startBtn.disabled = true;
  if (demoBtn) demoBtn.disabled = true;
  setRuntime(true, '字幕演示'); advanceDemo();
}
function stopDemo() {
  if (demoTimer) clearInterval(demoTimer);
  demoTimer = undefined;
  if (demoBtn) demoBtn.disabled = false;
  startBtn.disabled = runtimeMode !== 'LOCAL' || !modelsReady;
  stopBtn.disabled = !(socket && socket.readyState === WebSocket.OPEN);
  setRuntime(false, '待机');
}
async function runSystemAction(button, endpoint, body, busyMessage) {
  button.disabled = true;
  systemNotice.className = 'system-notice';
  systemNotice.textContent = busyMessage;
  try {
    const response = await fetch(endpoint, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.message || result.detail || '操作失败');
    await checkOllama();
    systemNotice.textContent = result.message || '操作完成';
    systemNotice.className = 'system-notice good';
  } catch (error) {
    systemNotice.className = 'system-notice warn';
    systemNotice.textContent = `操作未完成：${error.message}`;
  } finally { button.disabled = false; }
}
startBtn.addEventListener('click', startSession);
stopBtn.addEventListener('click', stopSession);
demoBtn?.addEventListener('click', startDemo);
clearBtn.addEventListener('click', () => { stopDemo(); captionRows = []; mockCaptionKeys.clear(); renderCaptions(); updateSummary(); });
exportBtn.addEventListener('click', exportTranscript);
floatingBtn?.addEventListener('click', () => setFloatingMode(!floatingMode));
tipsBtn?.addEventListener('click', () => toggleModal(tipsModal, true));
settingsBtn?.addEventListener('click', openSettings);
closeTipsBtn?.addEventListener('click', closeTips);
continueTipsBtn?.addEventListener('click', async () => { if (await closeTips()) await openSettings(); });
closeSettingsBtn?.addEventListener('click', () => toggleModal(settingsModal, false));
checkOllamaBtn?.addEventListener('click', checkOllama);
upgradeOllamaBtn?.addEventListener('click', () => runSystemAction(upgradeOllamaBtn, '/system/upgrade', {}, '正在尝试升级本地翻译引擎…'));
pullModelBtn?.addEventListener('click', () => runSystemAction(pullModelBtn, '/system/pull-model', { model: recommendedModelStatus.textContent }, '正在下载推荐翻译模型…'));
saveSettingsBtn?.addEventListener('click', saveModelDirectory);
chooseModelDirectoryBtn?.addEventListener('click', () => {
  if (window.webkit?.messageHandlers?.native) window.webkit.messageHandlers.native.postMessage({ type: 'choose_model_directory' });
  else modelDirectory?.focus();
});
sourceLanguage.addEventListener('change', () => { ensureDifferentLanguages('source'); updateSummary(); });
targetLanguage.addEventListener('change', () => { ensureDifferentLanguages('target'); updateSummary(); });
speakerMode.addEventListener('change', updateSummary);
inputDevice.addEventListener('change', updateSummary);
swapLanguagesBtn.addEventListener('click', swapLanguages);
directionButtons.forEach(button => button.addEventListener('click', () => setDirection(button.dataset.source, button.dataset.target)));
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  if (!settingsModal.hidden) toggleModal(settingsModal, false);
  else if (!tipsModal.hidden) closeTips();
  else if (floatingMode) setFloatingMode(false);
});
modeStatus.textContent = '演示'; modeBadge.textContent = '演示'; startBtn.disabled = true;
renderCaptions(); updateSummary(); loadDevices(); loadPreferences(); checkOllama();
if (serviceAddress) serviceAddress.textContent = location.host;
fetch('/health').then(response => response.json()).then(updateHealth).catch(() => { setDiagnostic('本地服务未连接，可先检查 App 状态'); });
setInterval(() => { fetch('/health').then(response => response.json()).then(updateHealth).catch(() => {}); }, 3000);
setInterval(() => {
  if (!socket || socket.readyState !== WebSocket.OPEN || !audioFrames || lastCaptionAt) return;
  if (sessionStartedAt && Date.now() - sessionStartedAt > 7000) setDiagnostic('已收到音频，但暂未检测到语音；请提高音量或检查输入设备');
}, 2000);
