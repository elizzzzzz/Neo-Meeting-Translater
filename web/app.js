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
    modelReadiness.textContent = models.ready ? '模型可用 · 热启动' : `${Math.round(Number(models.progress || 0))}% · ${models.message || '模型加载中'}`;
    modelReadiness.classList.toggle('ready', Boolean(models.ready));
    modelReadiness.classList.toggle('error', models.stage === 'error');
  }
  if (runtimeMode === 'LOCAL' && models.stage !== 'error') {
    startBtn.disabled = !models.ready || (socket && socket.readyState === WebSocket.OPEN);
    if (!models.ready) setDiagnostic(models.message || '模型正在冷启动，请稍候');
  }
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
  if (modelDirectory && health.settings?.model_dir) modelDirectory.value = health.settings.model_dir;
}

function toggleModal(modal, visible) {
  if (!modal) return;
  modal.hidden = !visible;
  if (visible) modal.querySelector('button, input')?.focus();
}
function closeTips() {
  if (rememberTips?.checked) localStorage.setItem('lmi.tips.dismissed', '1');
  toggleModal(tipsModal, false);
}
function openSettings() {
  toggleModal(settingsModal, true);
  checkOllama();
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
  if (!navigator.mediaDevices?.enumerateDevices) return;
  try {
    const devices = await navigator.mediaDevices.enumerateDevices(); const inputs = devices.filter((device) => device.kind === 'audioinput');
    inputDevice.innerHTML = inputs.length ? inputs.map((device, index) => `<option value="${escapeHtml(device.deviceId)}">${escapeHtml(device.label || `音频输入 ${index + 1}`)}</option>`).join('') : '<option value="">默认音频输入</option>';
    updateSummary();
  } catch { inputDevice.innerHTML = '<option value="">默认音频输入</option>'; sourceStatus.textContent = '设备读取失败'; }
}
async function startSession() {
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
  socket.onclose = () => { cleanupAudio(); startBtn.disabled = false; stopBtn.disabled = true; setRuntime(false, '已停止'); };
  socket.onerror = () => { setDiagnostic('本地服务连接失败'); setRuntime(false, '连接失败'); };
}
function cleanupAudio() { if (processor) processor.disconnect(); if (audioContext) audioContext.close(); if (mediaStream) mediaStream.getTracks().forEach((track) => track.stop()); processor = null; audioContext = null; mediaStream = null; }
function stopSession() { if (socket && socket.readyState === WebSocket.OPEN) socket.close(); else cleanupAudio(); }
function exportTranscript() { const text = captionRows.map((row) => `[${formatTime(row.start_ms)}] ${row.speaker_id}\n${row.original_text}\n${row.translated_text || ''}`).join('\n\n'); const blob = new Blob([text || '暂无字幕'], { type: 'text/plain;charset=utf-8' }); const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `meeting-${new Date().toISOString().slice(0, 10)}.txt`; link.click(); URL.revokeObjectURL(link.href); }

startBtn.addEventListener('click', startSession); stopBtn.addEventListener('click', stopSession); clearBtn.addEventListener('click', () => { captionRows = []; renderCaptions(); updateSummary(); }); exportBtn.addEventListener('click', exportTranscript); floatingBtn?.addEventListener('click', () => setFloatingMode(!floatingMode)); tipsBtn?.addEventListener('click', () => toggleModal(tipsModal, true)); settingsBtn?.addEventListener('click', openSettings); closeTipsBtn?.addEventListener('click', closeTips); continueTipsBtn?.addEventListener('click', () => { closeTips(); openSettings(); }); closeSettingsBtn?.addEventListener('click', () => toggleModal(settingsModal, false)); checkOllamaBtn?.addEventListener('click', checkOllama); upgradeOllamaBtn?.addEventListener('click', async () => { upgradeOllamaBtn.disabled = true; systemNotice.textContent = '正在尝试升级 Ollama…'; const response = await fetch('/system/upgrade', { method: 'POST' }); const result = await response.json(); systemNotice.textContent = result.message || '升级完成，请重新检查'; upgradeOllamaBtn.disabled = false; await checkOllama(); }); pullModelBtn?.addEventListener('click', async () => { pullModelBtn.disabled = true; systemNotice.textContent = '正在下载推荐翻译模型，首次可能需要几分钟…'; const response = await fetch('/system/pull-model', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model: recommendedModelStatus.textContent }) }); const result = await response.json(); systemNotice.textContent = result.message || '模型下载完成'; await checkOllama(); }); saveSettingsBtn?.addEventListener('click', saveModelDirectory); chooseModelDirectoryBtn?.addEventListener('click', () => { if (window.webkit?.messageHandlers?.native) window.webkit.messageHandlers.native.postMessage({ type: 'choose_model_directory' }); else { const selected = window.prompt('输入模型保存目录', modelDirectory?.value || ''); if (selected && modelDirectory) modelDirectory.value = selected; } }); sourceLanguage.addEventListener('change', () => { ensureDifferentLanguages('source'); updateSummary(); }); targetLanguage.addEventListener('change', () => { ensureDifferentLanguages('target'); updateSummary(); }); speakerMode.addEventListener('change', updateSummary); inputDevice.addEventListener('change', updateSummary); swapLanguagesBtn.addEventListener('click', swapLanguages); directionButtons.forEach((button) => button.addEventListener('click', () => setDirection(button.dataset.source, button.dataset.target))); modeStatus.textContent = '演示'; modeBadge.textContent = '演示'; renderCaptions(); updateSummary(); loadDevices();
if (serviceAddress) serviceAddress.textContent = location.host;
fetch('/health').then((response) => response.json()).then(updateHealth).catch(() => { diagnosticStatus.textContent = '无法读取服务状态'; });
fetch('/system/check').then((response) => response.json()).then(() => { if (!localStorage.getItem('lmi.tips.dismissed')) toggleModal(tipsModal, true); }).catch(() => { if (!localStorage.getItem('lmi.tips.dismissed')) toggleModal(tipsModal, true); });
fetch('/settings').then((response) => response.json()).then((settings) => { if (modelDirectory && settings.model_dir) modelDirectory.value = settings.model_dir; }).catch(() => {});
setInterval(() => { fetch('/health').then((response) => response.json()).then(updateHealth).catch(() => {}); }, 3000);
setInterval(() => {
  if (!socket || socket.readyState !== WebSocket.OPEN || !audioFrames || lastCaptionAt) return;
  if (sessionStartedAt && Date.now() - sessionStartedAt > 7000) setDiagnostic('已收到音频，但暂未检测到语音；请提高音量或检查输入设备');
}, 2000);
