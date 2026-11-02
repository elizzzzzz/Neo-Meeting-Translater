const inputDevice = document.querySelector('#inputDevice');
const sourceLanguage = document.querySelector('#sourceLanguage');
const targetLanguage = document.querySelector('#targetLanguage');
const speakerMode = document.querySelector('#speakerMode');
const startBtn = document.querySelector('#startBtn');
const stopBtn = document.querySelector('#stopBtn');
const swapLanguagesBtn = document.querySelector('#swapLanguages');
const exportBtn = document.querySelector('#exportBtn');
const clearBtn = document.querySelector('#clearBtn');
const captions = document.querySelector('#captions');
const captionCount = document.querySelector('#captionCount');
const runtimeDot = document.querySelector('#runtimeDot');
const runtimeText = document.querySelector('#runtimeText');
const sessionLabel = document.querySelector('#sessionLabel');
const sourceStatus = document.querySelector('#sourceStatus');
const directionStatus = document.querySelector('#directionStatus');
const speakerStatus = document.querySelector('#speakerStatus');
const modeStatus = document.querySelector('#modeStatus');
const modeBadge = document.querySelector('#modeBadge');
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
const CALIBRATION_FRAMES = 12;
let noiseSamples = [];
let noiseFloorRms = VOICE_RMS_THRESHOLD;
let noiseFloorPeak = VOICE_PEAK_THRESHOLD;
let voiceHits = 0;

function resetVoiceDetection() {
  noiseSamples = [];
  noiseFloorRms = VOICE_RMS_THRESHOLD;
  noiseFloorPeak = VOICE_PEAK_THRESHOLD;
  voiceHits = 0;
}

function setRuntime(active, text) { runtimeDot.classList.toggle('active', active); runtimeText.textContent = text; }
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
  captions.lastElementChild?.scrollIntoView({ block: 'nearest' });
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
  const candidate = rms >= Math.max(VOICE_RMS_THRESHOLD, noiseFloorRms * 2.5)
    && peak >= Math.max(VOICE_PEAK_THRESHOLD, noiseFloorPeak * 2.2);
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
  if (!navigator.mediaDevices?.getUserMedia) {
    sessionLabel.textContent = '当前浏览器不支持麦克风输入，请使用最新 Chrome 或 Edge。';
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
      processor.onaudioprocess = (event) => { if (socket.readyState !== WebSocket.OPEN) return; const pcm = downsample(event.inputBuffer.getChannelData(0), audioContext.sampleRate, 16000); if (!containsVoice(pcm)) return; const label = inputDevice.options[inputDevice.selectedIndex]?.textContent || ''; const sourceType = /blackhole|loopback|virtual/i.test(label) ? 'meeting_loopback' : 'microphone'; socket.send(JSON.stringify({ type: 'audio', session_id: sourceType, audio_base64: encodePcm(pcm), sample_rate: 16000, channels: 1, source: sourceType })); };
      const silentOutput = audioContext.createGain(); silentOutput.gain.value = 0;
      source.connect(processor); processor.connect(silentOutput); silentOutput.connect(audioContext.destination); stopBtn.disabled = false; sessionLabel.textContent = sourceStatus.textContent; setRuntime(true, '运行中');
    } catch (error) { cleanupAudio(); sessionLabel.textContent = `音频输入失败：${error.message || '请检查系统麦克风权限'}`; if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) socket.close(); }
  };
  socket.onmessage = (message) => {
    const event = JSON.parse(message.data);
    if (event.type === 'caption') {
      const captionKey = `${event.original_text || ''}\u0000${event.translated_text || ''}`;
      if (runtimeMode === 'MOCK' && mockCaptionKeys.has(captionKey)) return;
      if (runtimeMode === 'MOCK') mockCaptionKeys.add(captionKey);
      captionRows.push(event); renderCaptions(); updateSummary();
    }
    if (event.type === 'error') sessionLabel.textContent = event.message;
  };
  socket.onclose = () => { cleanupAudio(); startBtn.disabled = false; stopBtn.disabled = true; setRuntime(false, '已停止'); };
  socket.onerror = () => { sessionLabel.textContent = '本地服务连接失败'; setRuntime(false, '连接失败'); };
}
function cleanupAudio() { if (processor) processor.disconnect(); if (audioContext) audioContext.close(); if (mediaStream) mediaStream.getTracks().forEach((track) => track.stop()); processor = null; audioContext = null; mediaStream = null; }
function stopSession() { if (socket && socket.readyState === WebSocket.OPEN) socket.close(); else cleanupAudio(); }
function exportTranscript() { const text = captionRows.map((row) => `[${formatTime(row.start_ms)}] ${row.speaker_id}\n${row.original_text}\n${row.translated_text || ''}`).join('\n\n'); const blob = new Blob([text || '暂无字幕'], { type: 'text/plain;charset=utf-8' }); const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `meeting-${new Date().toISOString().slice(0, 10)}.txt`; link.click(); URL.revokeObjectURL(link.href); }

startBtn.addEventListener('click', startSession); stopBtn.addEventListener('click', stopSession); clearBtn.addEventListener('click', () => { captionRows = []; renderCaptions(); updateSummary(); }); exportBtn.addEventListener('click', exportTranscript); sourceLanguage.addEventListener('change', () => { ensureDifferentLanguages('source'); updateSummary(); }); targetLanguage.addEventListener('change', () => { ensureDifferentLanguages('target'); updateSummary(); }); speakerMode.addEventListener('change', updateSummary); inputDevice.addEventListener('change', updateSummary); swapLanguagesBtn.addEventListener('click', swapLanguages); directionButtons.forEach((button) => button.addEventListener('click', () => setDirection(button.dataset.source, button.dataset.target))); modeStatus.textContent = 'Mock'; modeBadge.textContent = 'MOCK'; renderCaptions(); updateSummary(); loadDevices();
if (serviceAddress) serviceAddress.textContent = location.host;
fetch('/health').then((response) => response.json()).then((health) => { runtimeMode = String(health.mode || 'mock').toUpperCase(); modeStatus.textContent = runtimeMode; modeBadge.textContent = runtimeMode; }).catch(() => {});
