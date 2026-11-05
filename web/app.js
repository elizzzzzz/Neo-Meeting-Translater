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
const interfaceLanguage = document.querySelector('#interfaceLanguage');
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
const asrEngine = document.querySelector('#asrEngine');
const asrEngineHint = document.querySelector('#asrEngineHint');
const asrModelStatus = document.querySelector('#asrModelStatus');
const downloadAsrBtn = document.querySelector('#downloadAsrBtn');
const chooseModelDirectoryBtn = document.querySelector('#chooseModelDirectoryBtn');
const checkOllamaBtn = document.querySelector('#checkOllamaBtn');
const installOllamaBtn = document.querySelector('#installOllamaBtn');
const upgradeOllamaBtn = document.querySelector('#upgradeOllamaBtn');
const pullModelBtn = document.querySelector('#pullModelBtn');
const saveSettingsBtn = document.querySelector('#saveSettingsBtn');
const captions = document.querySelector('#captions');
const captionCount = document.querySelector('#captionCount');
const latestBtn = document.querySelector('#latestBtn');
const changeSpeakerBtn = document.querySelector('#changeSpeakerBtn');
const runtimeDot = document.querySelector('#runtimeDot');
const runtimeText = document.querySelector('#runtimeText');
const modelReadiness = document.querySelector('#modelReadiness');
const sessionLabel = document.querySelector('#sessionLabel');
const sourceStatus = document.querySelector('#sourceStatus');
const directionStatus = document.querySelector('#directionStatus');
const speakerStatus = document.querySelector('#speakerStatus');
const modeStatus = document.querySelector('#modeStatus');
const modeBadge = document.querySelector('#modeBadge');
const captionDisplayMode = document.querySelector('#captionDisplayMode');
const captionSourceHeader = document.querySelector('#captionSourceHeader');
const captionTranslationHeader = document.querySelector('#captionTranslationHeader');
const asrStatus = document.querySelector('#asrStatus');
const ollamaStatus = document.querySelector('#ollamaStatus');
const ollamaModelStatus = document.querySelector('#ollamaModelStatus');
const translationStatus = document.querySelector('#translationStatus');
const audioStatus = document.querySelector('#audioStatus');
const inputLevelStatus = document.querySelector('#inputLevelStatus');
const inputLevelMeter = document.querySelector('#inputLevelMeter');
const recognitionLanguageStatus = document.querySelector('#recognitionLanguageStatus');
const diagnosticStatus = document.querySelector('#diagnosticStatus');
const directionPill = document.querySelector('#directionPill');
const serviceAddress = document.querySelector('#serviceAddress');
const directionButtons = [...document.querySelectorAll('.direction-button')];

let socket;
let audioContext;
let mediaStream;
let activeInputLabel = '';
let pendingAudio = new Float32Array();
let queuedAudioMs = 0;
let pendingTranslations = 0;
let audioInFlight = false;
let pendingBoundaryAudio = null;
let pendingSpeakerBoundary = false;
let sessionEnding = false;
let finishSent = false;
let captureSessionId = '';
let captureSessionSequence = 0;
let processor;
let captionRows = [];
let followCaptions = true;
let speakerChoiceMade = false;
let runtimeMode = 'MOCK';
const mockCaptionKeys = new Set();
let audioFrames = 0;
let lastCaptionAt = 0;
let sessionStartedAt = 0;
let floatingMode = false;
let selectedLanguagePair = 'zh-ja';
const LANGUAGE_LABELS = {zh: '中文', en: 'English', ja: '日本語'};
const LANGUAGE_PAIRS = ['zh-ja', 'zh-en', 'en-ja'];
let modelsReady = false;
let lastHealth = null;
let demoTimer;
let demoStep = 0;
let demoSession = "";
let lastInputRms = 0;

const UI_TEXT = {
  zh: {
    'brand.name': 'LOCAL INTERPRETER', 'nav.workspace': 'MEETING WORKSPACE', 'nav.liveMeeting': '实时会议',
    'mode.local': '本地', 'mode.demo': '演示', 'language.interface': '界面语言', 'language.auto': '自动', 'language.zh': '中文', 'language.ja': '日本語', 'language.en': 'English',
    'language.autoDetect': '自动识别', 'language.zhSimplified': '中文（简体）',
    'actions.guide': '使用指南', 'actions.settings': '本地设置', 'actions.subtitleMode': '字幕模式', 'actions.exitSubtitleMode': '退出字幕模式', 'actions.export': '导出记录', 'actions.startAudio': '开启音频输入', 'actions.stop': '停止', 'actions.latest': '回到最新 ↓', 'actions.clear': '清空', 'actions.floating': '字幕浮窗', 'actions.exitFloating': '退出浮窗',
    'status.localRun': '本地运行', 'status.liveText': '实时文字', 'intro.title': '把会议内容留在本机。', 'intro.description': '实时识别、区分说话人，并生成中日、中英、英日双向字幕。', 'transcript.segments': '段发言', 'tips.kicker': '使用提示', 'tips.title': '三步开始本地会议翻译', 'tips.lead': '所有音频和模型都留在这台 Mac 上。字幕模式只显示已经收到的真实原文和译文，不生成模拟内容。', 'tips.audioTitle': '选音频', 'tips.audioBody': '麦克风用于现场会议；腾讯会议、Teams 和网页视频请选择 BlackHole、Loopback 等系统回环设备。', 'tips.modelTitle': '等模型就绪', 'tips.modelBody': '顶部显示冷启动进度。看到“模型可用 · 热启动”后再开始会议。', 'tips.floatingTitle': '需要时开浮窗', 'tips.floatingBody': '点击“字幕模式”，字幕会置顶、半透明并可拖动、缩放到会议窗口空白处。', 'tips.remember': '以后不再提醒', 'actions.later': '稍后再看', 'actions.setup': '开始设置', 'actions.close': '关闭', 'settings.kicker': '本机环境', 'settings.title': '模型与 Ollama 设置', 'settings.ollamaInstall': 'Ollama 安装', 'settings.version': '当前版本', 'settings.recommendedModel': '推荐翻译模型', 'settings.modelStatus': '模型状态', 'settings.asrEngine': '语音转文字引擎', 'settings.prepareAsr': '准备语音模型', 'settings.captionContent': '字幕显示内容', 'settings.bilingual': '双语对照：源与译', 'settings.sourceOnly': '仅显示源文', 'settings.translationOnly': '仅显示译文', 'settings.captionHint': '中日：中文左、日文右；中英：中文左、英文右；英日：英文左、日文右。“源 / 译”随实际发言切换。', 'settings.modelDirectory': '模型保存目录', 'settings.chooseDirectory': '选择目录', 'settings.directoryHint': '此目录用于语音识别模型缓存，更改后重启生效。现有文件不会自动迁移；Ollama 翻译模型目前由其自身管理。', 'settings.onlineAudio': '在线会议 / 网页视频音频', 'settings.onlineAudioHint': '系统音频捕获需要 macOS 音频回环设备。安装 BlackHole 或 Loopback 后，在主界面的“音频输入”中选择对应设备；应用不会把会议音频上传到网络。', 'settings.recheck': '重新检查', 'settings.installOllama': '安装 Ollama', 'settings.upgradeOllama': '升级 Ollama', 'settings.installModel': '安装推荐模型', 'settings.save': '保存设置', 'footer.config': '文字模式 · M3 / 16G 配置', 'footer.service': '服务地址',
    'controls.ariaLabel': '会议输入设置', 'controls.audioInput': '音频输入', 'controls.defaultMic': '默认麦克风（授权后显示名称）', 'controls.sourceLanguage': '源语言', 'controls.targetLanguage': '目标语言', 'controls.speaker': '说话人',
    'speaker.manual': '手动换人', 'speaker.autoTest': '自动分人（测试）', 'direction.ariaLabel': '翻译方向快捷设置', 'direction.eyebrow': 'TRANSLATION DIRECTIONS', 'direction.title': '选择会议语言', 'direction.hint': '双方轮流发言，自动识别与互译',
    'transcript.eyebrow': 'LIVE TRANSCRIPT', 'transcript.title': '发言记录', 'transcript.footnote': '同一发言人连续记录 · 向上滚动查看历史，回到底部继续跟随', 'session.waitingAudio': '等待音频输入', 'status.eyebrow': 'SESSION', 'status.title': '当前状态', 'status.inputSource': '输入来源', 'status.inputLevel': '输入电平', 'status.recognitionLanguage': '识别语言', 'status.direction': '方向', 'status.speakerMode': '说话人模式', 'status.runMode': '运行模式', 'status.asr': '语音识别', 'status.ollama': '翻译引擎', 'status.translationModel': '翻译模型', 'status.translation': '翻译状态', 'status.audio': '音频链路', 'status.diagnostic': '诊断',
    'status.loading': '加载中', 'status.ready': '已就绪', 'status.running': '运行中', 'status.processing': '推理中', 'status.configured': '已配置', 'status.offline': '未连接', 'status.missing': '缺少模型', 'status.error': '错误', 'status.mock': '演示', 'status.unknown': '未知',
    'language.locked': '已锁定{language}', 'language.autoDetected': '自动识别', 'language.zhName': '中文', 'language.jaName': '日语', 'language.enName': '英语',
    'caption.waiting': '等待实时字幕', 'caption.emptyHint': '选择麦克风或 BlackHole 回环设备后开始会议。', 'caption.translationPending': '翻译处理中…', 'caption.translationUpdating': '译文更新中',
    'runtime.idle': '待机', 'runtime.connecting': '连接中…', 'runtime.preparing': '准备收音…', 'runtime.running': '运行中', 'runtime.stopped': '已停止', 'runtime.unavailable': '不可用', 'runtime.finishing': '正在收尾', 'runtime.paused': '收音已暂停',
  },
  ja: {
    'brand.name': 'LOCAL INTERPRETER', 'nav.workspace': 'MEETING WORKSPACE', 'nav.liveMeeting': 'リアルタイム会議', 'mode.local': 'ローカル', 'mode.demo': 'デモ', 'language.interface': '表示言語', 'language.auto': '自動', 'language.zh': '中文', 'language.ja': '日本語', 'language.en': 'English', 'language.autoDetect': '自動認識', 'language.zhSimplified': '中国語（簡体字）',
    'actions.guide': '使い方', 'actions.settings': 'ローカル設定', 'actions.subtitleMode': '字幕モード', 'actions.exitSubtitleMode': '字幕モードを終了', 'actions.export': '記録を書き出す', 'actions.startAudio': '音声入力を開始', 'actions.stop': '停止', 'actions.latest': '最新へ ↓', 'actions.clear': 'クリア', 'actions.floating': '字幕フロート', 'actions.exitFloating': 'フロートを終了',
    'status.localRun': 'ローカル実行', 'status.liveText': 'リアルタイム文字', 'intro.title': '会議の内容をこの Mac に保存。', 'intro.description': '発話を認識し、話者を分けて中日・中英・英日を双方向に字幕化します。', 'transcript.segments': '発話', 'tips.kicker': '使い方', 'tips.title': '3 ステップでローカル会議翻訳', 'tips.lead': '音声とモデルはこの Mac に保存されます。字幕モードは受信した実際の原文と訳文だけを表示します。', 'tips.audioTitle': '音声を選択', 'tips.audioBody': '現地会議はマイク、Teams・Tencent Meeting・Web 動画は BlackHole や Loopback を選択します。', 'tips.modelTitle': 'モデルを待つ', 'tips.modelBody': '上部にコールドスタートの進捗が表示されます。「モデル準備完了 · ウォーム」を確認してから開始します。', 'tips.floatingTitle': 'フロートを使う', 'tips.floatingBody': '字幕モードは最前面・半透明で、会議画面の空き場所へ移動できます。', 'tips.remember': '次回から表示しない', 'actions.later': '後で', 'actions.setup': '設定を開始', 'actions.close': '閉じる', 'settings.kicker': 'ローカル環境', 'settings.title': 'モデルと Ollama の設定', 'settings.ollamaInstall': 'Ollama のインストール', 'settings.version': '現在のバージョン', 'settings.recommendedModel': '推奨翻訳モデル', 'settings.modelStatus': 'モデル状態', 'settings.asrEngine': '音声認識エンジン', 'settings.prepareAsr': '音声モデルを準備', 'settings.captionContent': '字幕の表示内容', 'settings.bilingual': '対訳：原文と訳文', 'settings.sourceOnly': '原文のみ', 'settings.translationOnly': '訳文のみ', 'settings.captionHint': '中日：中国語を左、日本語を右。中英：中国語を左、英語を右。英日：英語を左、日本語を右。原文と訳文の表示は発話ごとに切り替わります。', 'settings.modelDirectory': 'モデル保存先', 'settings.chooseDirectory': 'フォルダを選択', 'settings.directoryHint': '音声認識モデルのキャッシュ先です。変更後は App を再起動してください。既存ファイルは移動しません。Ollama の翻訳モデルは Ollama が管理します。', 'settings.onlineAudio': 'オンライン会議 / Web 動画の音声', 'settings.onlineAudioHint': 'システム音声の取り込みには macOS のループバックデバイスが必要です。BlackHole または Loopback をインストールし、メイン画面で音声入力として選択します。音声はネットワークへ送信されません。', 'settings.recheck': '再チェック', 'settings.installOllama': 'Ollama をインストール', 'settings.upgradeOllama': 'Ollama を更新', 'settings.installModel': '推奨モデルをインストール', 'settings.save': '設定を保存', 'footer.config': '文字モード · M3 / 16G', 'footer.service': 'サービス',
    'controls.ariaLabel': '会議入力設定', 'controls.audioInput': '音声入力', 'controls.defaultMic': 'デフォルトマイク（許可後に表示）', 'controls.sourceLanguage': '原言語', 'controls.targetLanguage': '翻訳先', 'controls.speaker': '話者', 'speaker.manual': '手動で話者変更', 'speaker.autoTest': '自動話者分離（テスト）',
    'direction.ariaLabel': '翻訳方向のクイック設定', 'direction.eyebrow': 'TRANSLATION DIRECTIONS', 'direction.title': '会議の言語を選択', 'direction.hint': '交互に話す会議を自動認識して翻訳', 'transcript.eyebrow': 'LIVE TRANSCRIPT', 'transcript.title': '発話記録', 'transcript.footnote': '同じ話者を連続表示 · 上へスクロールして履歴を確認し、最下部で追従', 'session.waitingAudio': '音声入力を待機中', 'status.eyebrow': 'SESSION', 'status.title': '現在の状態', 'status.inputSource': '音声入力', 'status.inputLevel': '入力レベル', 'status.recognitionLanguage': '認識言語', 'status.direction': '方向', 'status.speakerMode': '話者モード', 'status.runMode': '実行モード', 'status.asr': '音声認識', 'status.ollama': '翻訳エンジン', 'status.translationModel': '翻訳モデル', 'status.translation': '翻訳状態', 'status.audio': '音声経路', 'status.diagnostic': '診断',
    'status.loading': '読み込み中', 'status.ready': '準備完了', 'status.running': '実行中', 'status.processing': '推論中', 'status.configured': '設定済み', 'status.offline': '未接続', 'status.missing': 'モデル不足', 'status.error': 'エラー', 'status.mock': 'デモ', 'status.unknown': '不明', 'language.locked': '{language} に固定', 'language.autoDetected': '自動認識', 'language.zhName': '中国語', 'language.jaName': '日本語', 'language.enName': '英語', 'caption.waiting': 'リアルタイム字幕を待機中', 'caption.emptyHint': 'マイクまたは BlackHole のループバックを選択して会議を開始します。', 'caption.translationPending': '翻訳中…', 'caption.translationUpdating': '翻訳を更新中', 'runtime.idle': '待機中', 'runtime.connecting': '接続中…', 'runtime.preparing': '音声入力を準備中…', 'runtime.running': '実行中', 'runtime.stopped': '停止', 'runtime.unavailable': '利用不可', 'runtime.finishing': '終了処理中', 'runtime.paused': '音声入力を一時停止',
  },
  en: {
    'brand.name': 'LOCAL INTERPRETER', 'nav.workspace': 'MEETING WORKSPACE', 'nav.liveMeeting': 'Live meeting', 'mode.local': 'Local', 'mode.demo': 'Demo', 'language.interface': 'Interface language', 'language.auto': 'Auto', 'language.zh': '中文', 'language.ja': '日本語', 'language.en': 'English', 'language.autoDetect': 'Auto detect', 'language.zhSimplified': 'Chinese (Simplified)',
    'actions.guide': 'Guide', 'actions.settings': 'Local settings', 'actions.subtitleMode': 'Subtitle mode', 'actions.exitSubtitleMode': 'Exit subtitle mode', 'actions.export': 'Export record', 'actions.startAudio': 'Start audio input', 'actions.stop': 'Stop', 'actions.latest': 'Back to latest ↓', 'actions.clear': 'Clear', 'actions.floating': 'Floating captions', 'actions.exitFloating': 'Exit floating mode',
    'status.localRun': 'Running locally', 'status.liveText': 'Live text', 'intro.title': 'Keep the meeting on this Mac.', 'intro.description': 'Recognize speech, separate speakers, and create two-way Chinese, Japanese, and English captions.', 'transcript.segments': 'segments', 'tips.kicker': 'Tips', 'tips.title': 'Start local meeting translation in three steps', 'tips.lead': 'Audio and models stay on this Mac. Subtitle mode only shows received source and translated text; it never invents sample output.', 'tips.audioTitle': 'Choose audio', 'tips.audioBody': 'Use a microphone for in-room meetings; choose BlackHole or Loopback for Tencent Meeting, Teams, and web video.', 'tips.modelTitle': 'Wait for models', 'tips.modelBody': 'Cold-start progress appears at the top. Start when you see “Models ready · warm”.', 'tips.floatingTitle': 'Use floating captions', 'tips.floatingBody': 'Subtitle mode stays on top, remains translucent, and can be moved over an empty area of the meeting window.', 'tips.remember': 'Do not show again', 'actions.later': 'Later', 'actions.setup': 'Start setup', 'actions.close': 'Close', 'settings.kicker': 'Local environment', 'settings.title': 'Model and Ollama settings', 'settings.ollamaInstall': 'Ollama installation', 'settings.version': 'Current version', 'settings.recommendedModel': 'Recommended translation model', 'settings.modelStatus': 'Model status', 'settings.asrEngine': 'Speech-to-text engine', 'settings.prepareAsr': 'Prepare speech model', 'settings.captionContent': 'Caption display', 'settings.bilingual': 'Bilingual: source and translation', 'settings.sourceOnly': 'Source only', 'settings.translationOnly': 'Translation only', 'settings.captionHint': 'Chinese/Japanese: Chinese left, Japanese right. Chinese/English: Chinese left, English right. English/Japanese: English left, Japanese right. Source and translation markers follow the speaker.', 'settings.modelDirectory': 'Model directory', 'settings.chooseDirectory': 'Choose folder', 'settings.directoryHint': 'Speech model cache directory. Restart the App after changing it. Existing files are not moved; Ollama manages translation models separately.', 'settings.onlineAudio': 'Online meeting / web video audio', 'settings.onlineAudioHint': 'System audio capture requires a macOS loopback device. Install BlackHole or Loopback, then choose it as the audio input. Audio stays local and is not uploaded.', 'settings.recheck': 'Check again', 'settings.installOllama': 'Install Ollama', 'settings.upgradeOllama': 'Update Ollama', 'settings.installModel': 'Install recommended model', 'settings.save': 'Save settings', 'footer.config': 'Text mode · M3 / 16G', 'footer.service': 'Service',
    'controls.ariaLabel': 'Meeting input settings', 'controls.audioInput': 'Audio input', 'controls.defaultMic': 'Default microphone (name appears after permission)', 'controls.sourceLanguage': 'Source language', 'controls.targetLanguage': 'Target language', 'controls.speaker': 'Speaker', 'speaker.manual': 'Manual speaker change', 'speaker.autoTest': 'Automatic speaker split (test)',
    'direction.ariaLabel': 'Quick translation direction settings', 'direction.eyebrow': 'TRANSLATION DIRECTIONS', 'direction.title': 'Choose meeting languages', 'direction.hint': 'Auto-detect and translate alternating speakers', 'transcript.eyebrow': 'LIVE TRANSCRIPT', 'transcript.title': 'Transcript', 'transcript.footnote': 'Keep consecutive speech together · scroll up for history and return to the bottom to follow', 'session.waitingAudio': 'Waiting for audio input', 'status.eyebrow': 'SESSION', 'status.title': 'Current status', 'status.inputSource': 'Audio input', 'status.inputLevel': 'Input level', 'status.recognitionLanguage': 'Recognition language', 'status.direction': 'Direction', 'status.speakerMode': 'Speaker mode', 'status.runMode': 'Run mode', 'status.asr': 'Speech recognition', 'status.ollama': 'Translation engine', 'status.translationModel': 'Translation model', 'status.translation': 'Translation status', 'status.audio': 'Audio path', 'status.diagnostic': 'Diagnostics',
    'status.loading': 'Loading', 'status.ready': 'Ready', 'status.running': 'Running', 'status.processing': 'Processing', 'status.configured': 'Configured', 'status.offline': 'Offline', 'status.missing': 'Model missing', 'status.error': 'Error', 'status.mock': 'Demo', 'status.unknown': 'Unknown', 'language.locked': 'Locked to {language}', 'language.autoDetected': 'Auto-detect', 'language.zhName': 'Chinese', 'language.jaName': 'Japanese', 'language.enName': 'English', 'caption.waiting': 'Waiting for live captions', 'caption.emptyHint': 'Choose a microphone or BlackHole loopback device to start the meeting.', 'caption.translationPending': 'Translation pending…', 'caption.translationUpdating': 'Updating translation', 'runtime.idle': 'Idle', 'runtime.connecting': 'Connecting…', 'runtime.preparing': 'Preparing audio…', 'runtime.running': 'Running', 'runtime.stopped': 'Stopped', 'runtime.unavailable': 'Unavailable', 'runtime.finishing': 'Finishing', 'runtime.paused': 'Audio paused',
  },
};

function detectInterfaceLanguage() {
  const locale = String(navigator.language || 'zh-CN');
  if (/^ja(?:-|$)/i.test(locale)) return 'ja';
  if (/^en(?:-|$)/i.test(locale)) return 'en';
  return 'zh';
}
function activeInterfaceLanguage() {
  const selected = interfaceLanguage?.value || 'auto';
  return selected === 'auto' ? detectInterfaceLanguage() : (UI_TEXT[selected] ? selected : 'zh');
}
function uiText(key, fallback = '') {
  const value = UI_TEXT[activeInterfaceLanguage()]?.[key] || UI_TEXT.zh?.[key] || fallback || key;
  return value;
}
function languageDisplayLabel(code) {
  const key = code === 'zh' ? 'language.zhName' : code === 'ja' ? 'language.jaName' : 'language.enName';
  return uiText(key, LANGUAGE_LABELS[code] || code);
}
function applyInterfaceLanguage() {
  const lang = activeInterfaceLanguage();
  if (document.documentElement) document.documentElement.lang = lang === 'zh' ? 'zh-CN' : lang === 'ja' ? 'ja-JP' : 'en-US';
  document.querySelectorAll('[data-i18n]').forEach(element => {
    const value = UI_TEXT[lang]?.[element.dataset.i18n];
    if (value) element.textContent = value;
  });
  document.querySelectorAll('[data-i18n-aria-label]').forEach(element => {
    const value = UI_TEXT[lang]?.[element.dataset.i18nAriaLabel];
    if (value) element.setAttribute('aria-label', value);
  });
  if (modeBadge) modeBadge.textContent = runtimeMode === 'LOCAL' ? uiText('mode.local') : uiText('mode.demo');
  if (floatingBtn) floatingBtn.textContent = floatingMode ? uiText('actions.exitFloating') : uiText('actions.floating');
  if (demoBtn && !floatingMode) demoBtn.textContent = uiText('actions.subtitleMode');
  updateCaptionHeaders(); updateSummary();
}
function setInterfaceLanguage(value) {
  const next = UI_TEXT[value] || value === 'auto' ? value : 'auto';
  try { localStorage.setItem('interfaceLanguage', next); } catch {}
  if (interfaceLanguage) interfaceLanguage.value = next;
  applyInterfaceLanguage();
}

function setDiagnostic(message) {
  diagnosticStatus.textContent = message;
  sessionLabel.textContent = message;
}
function formatModel(value) {
  const text = String(value || '未配置');
  return text.length > 28 ? `${text.slice(0, 25)}…` : text;
}
function statusText(value) {
  const key = String(value || '').toLowerCase();
  const labels = { loading: 'status.loading', ready: 'status.ready', running: 'status.running', processing: 'status.processing', configured: 'status.configured', offline: 'status.offline', missing: 'status.missing', error: 'status.error', mock: 'status.mock' };
  return uiText(labels[key] || 'status.unknown', String(value || uiText('status.unknown')));
}
function updateHealth(health) {
  lastHealth = health;
  runtimeMode = String(health.mode || 'mock').toUpperCase();
  const modeLabel = runtimeMode === 'LOCAL' ? uiText('mode.local') : uiText('mode.demo');
  modeStatus.textContent = modeLabel;
  modeBadge.textContent = modeLabel;
  const models = health.models || {};
  const wasModelsReady = modelsReady;
  if (modelReadiness) {
    modelsReady = Boolean(models.ready);
    modelReadiness.textContent = runtimeMode === 'MOCK' ? `${uiText('status.mock')} · ${activeInterfaceLanguage() === 'en' ? 'no live model' : activeInterfaceLanguage() === 'ja' ? '実モデル未使用' : '不使用真实模型'}` : models.ready ? (activeInterfaceLanguage() === 'en' ? 'Models ready · warm' : activeInterfaceLanguage() === 'ja' ? 'モデル準備完了 · ウォーム' : '模型可用 · 热启动') : `${Math.round(Number(models.progress || 0))}% · ${models.message || (activeInterfaceLanguage() === 'en' ? 'Models not ready' : activeInterfaceLanguage() === 'ja' ? 'モデル未準備' : '模型未就绪')}`;
    modelReadiness.classList.toggle('ready', Boolean(models.ready));
    modelReadiness.classList.toggle('error', models.stage === 'error');
  }
  startBtn.disabled = runtimeMode !== 'LOCAL' || !models.ready || Boolean(socket && socket.readyState <= WebSocket.OPEN) || Boolean(demoTimer);
  startBtn.title = runtimeMode !== 'LOCAL' ? '尚未连接真实模型，可先演示字幕和浮窗' : !models.ready ? '模型未就绪，请先检查本地设置' : '';
  if (runtimeMode === 'LOCAL' && !models.ready && !demoTimer) setDiagnostic(models.message || (activeInterfaceLanguage() === 'en' ? 'Models are not connected; subtitle mode is available' : activeInterfaceLanguage() === 'ja' ? 'モデル未接続。字幕モードを利用できます' : '模型未连接，可先使用字幕模式'));
  if (runtimeMode === 'LOCAL' && models.ready && !wasModelsReady && !demoTimer && !(socket && socket.readyState <= WebSocket.OPEN)) setDiagnostic(models.message || (activeInterfaceLanguage() === 'en' ? 'Models ready; you can start the meeting' : activeInterfaceLanguage() === 'ja' ? 'モデル準備完了。会議を開始できます' : '模型已就绪，可开始会议'));
  asrStatus.textContent = `${statusText(health.asr?.status)} · ${formatModel(health.asr?.model)}`;
  const speakerOption = speakerMode.querySelector('option[value="embedding"]');
  if (speakerOption) speakerOption.disabled = !health.speaker?.available;
  speakerMode.title = health.speaker?.message || '未连接声纹模型，可手动换人';
  if (health.speaker?.available && !speakerChoiceMade && !(socket && socket.readyState <= WebSocket.OPEN)) {
    speakerMode.value = 'embedding'; speakerChoiceMade = true; updateSummary();
  }
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
  translationStatus.textContent = `${statusText(health.translation?.status)}${responseMs}${pendingTranslations ? ` · 待处理 ${pendingTranslations} 段` : ""}`;
  const frames = Number(health.audio?.frames || 0);
  if (frames > audioFrames && !(socket && socket.readyState <= WebSocket.OPEN)) audioStatus.textContent = `已收到 ${frames} 帧`;
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
    asrEngine.value = settings.asr_engine || 'whisper';
    asrEngineHint.textContent = settings.sensevoice_available ? 'SenseVoice 模型已连接。中文可对比 SenseVoice；日语可先用 Whisper。切换后重新打开 App 生效。' : 'SenseVoice 模型未连接，暂请选择 Whisper。需要在模型目录的 asr/sensevoice 中放入 model.int8.onnx、tokens.txt 和 silero_vad.onnx。';
  } catch { setDiagnostic('无法读取本地设置'); }
  await checkAsrModel();
  await checkOllama();
}
async function checkAsrModel() {
  if (!asrModelStatus) return;
  asrModelStatus.textContent = '正在检查语音模型…';
  try {
    const response = await fetch(`/system/models?engine=${encodeURIComponent(asrEngine.value || 'whisper')}`);
    const info = await response.json();
    asrModelStatus.textContent = info.installed ? `${info.model} · 已连接` : `${info.model} · 未连接（${info.progress || 0}%）`;
    downloadAsrBtn.disabled = Boolean(info.installed) || asrEngine.value === 'sensevoice';
    downloadAsrBtn.textContent = info.installed ? '语音模型已就绪' : asrEngine.value === 'sensevoice' ? '请导入本地文件' : '下载 Whisper 模型';
  } catch (error) {
    asrModelStatus.textContent = `检查失败：${error.message || '本地服务不可用'}`;
    downloadAsrBtn.disabled = true;
  }
}
function describeSystem(info) {
  if (!info.installed) return '尚未检测到 Ollama。安装后可使用本地翻译引擎。';
  if (info.update_available) return `发现 Ollama 新版本 ${info.latest_version}，可点击“尝试升级 Ollama”。`;
  if (!info.reachable) return '已检测到 Ollama，暂时无法连接服务。请检查 Ollama 是否运行，稍后点击重新检查。';
  if (!info.recommended_model_present) return `Ollama 已运行，推荐模型 ${info.recommended_model} 尚未下载。`;
  return `Ollama 已安装并运行，推荐模型 ${info.recommended_model} 可用。`;
}
async function checkOllama() {
  if (systemNotice) { systemNotice.className = 'system-notice'; systemNotice.textContent = '正在检查 Ollama 和推荐模型…'; }
  ollamaInstallStatus.textContent = '检查中…'; ollamaVersionStatus.textContent = '检查中…'; recommendedModelPresence.textContent = '检查中…';
  try {
    const response = await fetch('/system/check');
    const info = await response.json();
    const recommended = info.recommended_model || 'translategemma:4b';
    ollamaInstallStatus.textContent = info.installed ? (info.reachable ? '已安装并运行' : '已安装，暂未连接') : '未安装';
    ollamaVersionStatus.textContent = info.version ? `${info.version} · ${info.version_check || '待核对'}` : '未检测到版本';
    recommendedModelStatus.textContent = recommended;
    recommendedModelPresence.textContent = !info.reachable ? '服务未连接，无法核对' : info.recommended_model_present ? '已下载，可直接使用' : '尚未下载';
    if (systemNotice) {
      systemNotice.textContent = describeSystem(info);
      systemNotice.className = `system-notice ${info.installed && info.recommended_model_present && !info.update_available ? 'good' : 'warn'}`;
    }
    upgradeOllamaBtn.disabled = !info.installed || !info.brew_available;
    if (installOllamaBtn) installOllamaBtn.disabled = Boolean(info.installed);
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
    const response = await fetch('/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model_dir: value, asr_engine: asrEngine.value || 'whisper' }) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || '保存失败');
    setDiagnostic('识别引擎与模型目录已保存，重新打开 App 后生效');
    if (systemNotice) { systemNotice.className = 'system-notice good'; systemNotice.textContent = `已保存识别设置与目录：${result.model_dir}。重新打开 App 后生效。`; }
  } catch (error) {
    if (systemNotice) { systemNotice.className = 'system-notice warn'; systemNotice.textContent = `保存失败：${error.message}`; }
  } finally { saveSettingsBtn.disabled = false; }
}
window.__onModelDirectorySelected = (path) => { if (modelDirectory) modelDirectory.value = path; };

function setSessionControls(active) {
  [inputDevice, sourceLanguage, targetLanguage, speakerMode, swapLanguagesBtn, ...directionButtons].forEach(control => {
    control.disabled = active;
    control.title = active ? '停止音频后可更改设置' : '';
  });
  if (demoBtn) demoBtn.disabled = false;
  changeSpeakerBtn.disabled = !active;
}
function updateRecognitionLanguage(language) {
  const name = language ? languageDisplayLabel(language) : '';
  recognitionLanguageStatus.textContent = name ? uiText('language.locked').replace('{language}', name) : uiText('language.autoDetected');
}

function setRuntime(active, text) { runtimeDot.classList.toggle('active', active); runtimeText.textContent = text; }
function setFloatingMode(enabled) {
  floatingMode = enabled;
  document.body.classList.toggle('floating-mode', enabled);
  if (floatingBtn) floatingBtn.textContent = enabled ? uiText('actions.exitFloating') : uiText('actions.floating');
  if (window.webkit?.messageHandlers?.native) {
    window.webkit.messageHandlers.native.postMessage({ type: 'floating', enabled });
  }
}
function updateSummary() {
  captionCount.textContent = String(transcriptParagraphs().length);
  const sourceLabel = sourceLanguage.options[sourceLanguage.selectedIndex]?.textContent || '自动识别';
  const targetLabel = targetLanguage.options[targetLanguage.selectedIndex]?.textContent || '中文（简体）';
  const direction = sourceLanguage.value === 'auto'
    ? `${selectedLanguagePair.split('-').map(languageDisplayLabel).join(' ↔ ')} · ${activeInterfaceLanguage() === 'en' ? 'auto translate' : activeInterfaceLanguage() === 'ja' ? '自動翻訳' : '自动互译'}`
    : `${sourceLabel} → ${targetLabel}`;
  directionStatus.textContent = direction;
  directionPill.textContent = direction;
  speakerStatus.textContent = speakerMode.options[speakerMode.selectedIndex]?.textContent || '稍后区分';
  sourceStatus.textContent = activeInputLabel || inputDevice.options[inputDevice.selectedIndex]?.textContent || '未选择';
  directionButtons.forEach(button => button.classList.toggle('selected', `${button.dataset.source}-${button.dataset.target}` === selectedLanguagePair));
}

function displayMode() {
  return captionDisplayMode?.value || 'both';
}

function pairForLanguages(source, target) {
  return LANGUAGE_PAIRS.find(pair => {
    const languages = pair.split('-');
    return source !== target && languages.includes(source) && languages.includes(target);
  });
}
function bilingualColumns(chunks) {
  // Each paragraph keeps its own language pair even after a later session
  // selects different languages. Language positions never follow the speaker.
  const pair = chunks[0]?.language_pair
    || pairForLanguages(chunks[0]?.source_language, chunks[0]?.target_language)
    || selectedLanguagePair;
  const [leftLanguage, rightLanguage] = pair.split('-');
  const source = chunks.map(chunk => ({role: '源', text: chunk.original_text, language: chunk.source_language}));
  const translation = chunks.map(chunk => ({role: '译', text: chunk.translated_text, language: chunk.target_language}));
  const left = [], right = [];
  chunks.forEach((chunk, index) => {
    if (chunk.source_language === rightLanguage) {
      left.push(translation[index]); right.push(source[index]);
    } else {
      left.push(source[index]); right.push(translation[index]);
    }
  });
  return {
    leftLanguage, rightLanguage,
    leftLabel: languageDisplayLabel(leftLanguage), rightLabel: languageDisplayLabel(rightLanguage),
    left, right, source, translation,
  };
}

function renderColumn(parts) {
  return parts.filter(part => part.text || part.role === '源').map(part =>
    `<span class="caption-part"><b class="caption-role ${part.role === '源' ? 'source-role' : 'translation-role'}">${part.role === '源' ? (activeInterfaceLanguage() === 'en' ? 'SRC' : activeInterfaceLanguage() === 'ja' ? '原' : '源') : (activeInterfaceLanguage() === 'en' ? 'TR' : activeInterfaceLanguage() === 'ja' ? '訳' : '译')}</b>${escapeHtml(part.text || uiText('caption.translationPending'))} </span>`
  ).join('');
}

function updateCaptionHeaders() {
  if (!captionSourceHeader || !captionTranslationHeader) return;
  const [left, right] = selectedLanguagePair.split('-');
  const mode = displayMode();
  captionSourceHeader.textContent = mode === 'source' ? (activeInterfaceLanguage() === 'en' ? 'Source' : activeInterfaceLanguage() === 'ja' ? '原文' : '源文') : mode === 'translation' ? (activeInterfaceLanguage() === 'en' ? 'Translation' : activeInterfaceLanguage() === 'ja' ? '翻訳' : '译文') : languageDisplayLabel(left);
  captionTranslationHeader.textContent = mode === 'both' ? languageDisplayLabel(right) : '';
}
function ensureDifferentLanguages(changed) {
  if (sourceLanguage.value !== 'auto' && sourceLanguage.value === targetLanguage.value) {
    const pair = selectedLanguagePair.split('-');
    const other = pair.find(language => language !== targetLanguage.value) || 'zh';
    if (changed === 'source') targetLanguage.value = other;
    else sourceLanguage.value = other;
  }
  const pair = sourceLanguage.value === 'auto'
    ? (selectedLanguagePair.split('-').includes(targetLanguage.value) ? selectedLanguagePair : pairForLanguages('zh', targetLanguage.value))
    : pairForLanguages(sourceLanguage.value, targetLanguage.value);
  if (pair) selectedLanguagePair = pair;
  updateCaptionHeaders();
}
function setDirection(source, target) {
  selectedLanguagePair = pairForLanguages(source, target) || selectedLanguagePair;
  sourceLanguage.value = 'auto';
  targetLanguage.value = target;
  updateSummary(); renderCaptions();
}
function swapLanguages() {
  if (sourceLanguage.value === 'auto') {
    targetLanguage.value = selectedLanguagePair.split('-').find(language => language !== targetLanguage.value);
  } else [sourceLanguage.value, targetLanguage.value] = [targetLanguage.value, sourceLanguage.value];
  updateSummary(); updateCaptionHeaders();
}

function formatTime(milliseconds) { const totalSeconds = Math.max(0, Math.round(milliseconds / 1000)); return `${String(Math.floor(totalSeconds / 60)).padStart(2, '0')}:${String(totalSeconds % 60).padStart(2, '0')}`; }
function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character])); }
function upsertCaption(event) {
  const index = captionRows.findIndex(row => row.session_id === event.session_id && row.segment_id === event.segment_id);
  if (index < 0) captionRows.push(event);
  else {
    const previous = captionRows[index];
    if (event.translation_source_text && event.translation_source_text !== previous.original_text) return;
    // Keep the last translation visible while its corrected source is translated.
    const sameDirection = previous.source_language === event.source_language && previous.target_language === event.target_language;
    captionRows[index] = {...event, translated_text: event.translated_text || (sameDirection ? previous.translated_text : '') || ''};
  }
}
function transcriptParagraphs() {
  const paragraphs = [];
  for (const row of captionRows) {
    let paragraph = paragraphs[paragraphs.length - 1];
    // A speaker paragraph can contain both Chinese and Japanese. The speaker
    // boundary, rather than a decoder language flip, decides when to start a
    // new paragraph.
    if (!paragraph || paragraph.speaker_id !== row.speaker_id || paragraph.session_id !== row.session_id
        || paragraph.language_pair !== row.language_pair
        || pairForLanguages(paragraph.source_language, paragraph.target_language) !== pairForLanguages(row.source_language, row.target_language)) {
      paragraph = {...row, original_text: '', translated_text: '', chunks: []};
      paragraphs.push(paragraph);
    }
    paragraph.chunks.push(row);
    paragraph.original_text = paragraph.chunks.map(chunk => chunk.original_text).filter(Boolean).join(' ');
    paragraph.translated_text = paragraph.chunks.map(chunk => chunk.translated_text).filter(Boolean).join(' ');
    paragraph.end_ms = row.end_ms;
    paragraph.is_final = paragraph.chunks.every(chunk => chunk.is_final);
  }
  return paragraphs;
}
function speakerLabel(id) {
  if (id === 'SPEAKER_PENDING') return '当前发言 · 未分人';
  const match = /^SPEAKER_(\d+)$/.exec(id);
  const manual = /^MANUAL_(\d+)$/.exec(id);
  if (manual) return `发言段 ${manual[1]} · 手动`;
  return match ? `发言人 ${Number(match[1]) + 1}` : id;
}
function returnToLatest() {
  followCaptions = true;
  captions.scrollTop = captions.scrollHeight;
  latestBtn.hidden = true;
}
function renderCaptions() {
  const scrollTop = captions.scrollTop;
  updateCaptionHeaders();
  if (!captionRows.length) { captions.innerHTML = `<div class="empty-state"><strong>${uiText('caption.waiting')}</strong><span>${uiText('caption.emptyHint')}</span></div>`; return; }
  const paragraphs = transcriptParagraphs();
  const mode = displayMode();
  captions.dataset.displayMode = mode;
  const markup = paragraphs.map(event => {
    const columns = bilingualColumns(event.chunks);
    const pending = event.is_final ? '' : `<span class="draft">${uiText('caption.translationUpdating')}</span>`;
    const copies = mode === 'both'
      ? `<div class="caption-copy caption-left" lang="${columns.leftLanguage}">${renderColumn(columns.left)}</div><div class="caption-copy caption-right" lang="${columns.rightLanguage}">${renderColumn(columns.right)}</div>`
      : `<div class="caption-copy caption-left">${renderColumn(mode === 'source' ? columns.source : columns.translation)}</div>`;
    return `<section class="caption-row ${mode !== 'both' ? 'single-source' : ''}"><div class="caption-meta"><span class="speaker-chip">${escapeHtml(speakerLabel(event.speaker_id))}</span><span class="caption-time">${formatTime(event.start_ms)} — ${formatTime(event.end_ms)}</span>${pending}</div>${copies}</section>`;
  }).join('');
  if (captions.innerHTML !== markup) captions.innerHTML = markup;
  if (followCaptions) captions.scrollTop = captions.scrollHeight;
  else captions.scrollTop = scrollTop;
  latestBtn.hidden = followCaptions;
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
function sendPendingAudio() {
  if (audioInFlight || !socket || socket.readyState !== WebSocket.OPEN) return;
  let pcm;
  if (pendingBoundaryAudio?.length) { pcm = pendingBoundaryAudio.subarray(0, 12800); pendingBoundaryAudio = pendingBoundaryAudio.length > 12800 ? pendingBoundaryAudio.slice(12800) : null; }
  else if (pendingSpeakerBoundary) {
    pendingSpeakerBoundary = false; pendingBoundaryAudio = null; audioInFlight = true;
    socket.send(JSON.stringify({type:'speaker_change'})); return;
  } else {
    if (!pendingAudio.length) {
      if (sessionEnding && !finishSent) { finishSent = true; audioInFlight = true; socket.send(JSON.stringify({type:'finish'})); }
      return;
    }
    pcm = pendingAudio.subarray(0, 12800); pendingAudio = pendingAudio.slice(pcm.length);
  }
  audioInFlight = true;
  const sourceType = /blackhole|loopback|virtual/i.test(activeInputLabel) ? 'meeting_loopback' : 'microphone';
  socket.send(JSON.stringify({type:'audio',session_id:captureSessionId,audio_base64:encodePcm(pcm),sample_rate:16000,channels:1,source:sourceType}));
}
function requestSpeakerChange() {
  if (!socket || socket.readyState !== WebSocket.OPEN || pendingSpeakerBoundary || pendingBoundaryAudio) return;
  changeSpeakerBtn.disabled = true;
  pendingBoundaryAudio = pendingAudio; pendingAudio = new Float32Array(); pendingSpeakerBoundary = true;
  setDiagnostic('正在保留上一段发言并标记换人…');
  sendPendingAudio();
}
function queueAudioFrame(pcm) {
  // The server acknowledges after writing PCM to its local spool, independently
  // of inference. Keep every sample during a temporary service stall.
  if (pendingAudio.length + pcm.length > 16000 * 30) {
    stopCapture(); sessionEnding = true;
    setRuntime(false, '收音已暂停');
    setDiagnostic('服务积压超过 30 秒，已暂停收音；已接收音频继续处理，请稍后重新开始');
  }
  const next = new Float32Array(pendingAudio.length + pcm.length);
  next.set(pendingAudio); next.set(pcm, pendingAudio.length); pendingAudio = next;
  if (pendingAudio.length > 16000) audioStatus.textContent = `音频待送 ${(pendingAudio.length / 16000).toFixed(1)} 秒 · 完整保留`;

  sendPendingAudio();
}
function updateInputLevel(buffer) {
  let sumSquares = 0;
  for (const sample of buffer) sumSquares += sample * sample;
  lastInputRms = buffer.length ? Math.sqrt(sumSquares / buffer.length) : 0;
  const db = lastInputRms ? Math.max(-90, Math.round(20 * Math.log10(lastInputRms))) : -90;
  inputLevelMeter.value = Math.max(0, (db + 60) / 60);
  inputLevelStatus.textContent = lastInputRms < .0003 ? '无输入 / 静音' : `${lastInputRms < .003 ? '音量较低' : '收到声音'} · ${db} dB`;
}
async function loadDevices(activeTrack = null) {
  if (!navigator.mediaDevices?.enumerateDevices) {
    inputDevice.innerHTML = '<option value="">默认麦克风（授权后显示名称）</option>';
    updateSummary(); return;
  }
  try {
    const selected = activeTrack?.getSettings?.().deviceId || inputDevice.value;
    const devices = await navigator.mediaDevices.enumerateDevices(); const inputs = devices.filter((device) => device.kind === 'audioinput');
    inputDevice.innerHTML = inputs.length ? inputs.map((device, index) => `<option value="${escapeHtml(device.deviceId)}">${escapeHtml(device.label || `音频输入 ${index + 1}`)}</option>`).join('') : '<option value="">默认音频输入</option>';
    if (inputs.some(device => device.deviceId === selected)) inputDevice.value = selected;
    const active = inputs.find(device => device.deviceId === selected);
    if (activeTrack) activeInputLabel = activeTrack.label || active?.label || '默认麦克风（名称不可用）';
    updateSummary();
  } catch { inputDevice.innerHTML = '<option value="">默认音频输入</option>'; sourceStatus.textContent = '设备读取失败'; }
}
async function startSession() {
  if (runtimeMode !== 'LOCAL' || !modelsReady || (socket && socket.readyState <= WebSocket.OPEN)) return;
  stopDemo(); lastCaptionAt = 0;
  startBtn.disabled = true; setRuntime(false, '连接中…');
  setSessionControls(true);
  pendingAudio = new Float32Array(); queuedAudioMs = 0; pendingTranslations = 0; audioInFlight = false; pendingBoundaryAudio = null; pendingSpeakerBoundary = false; sessionEnding = false; finishSent = false;
  recognitionLanguageStatus.textContent = '等待服务确认';
  updateInputLevel(new Float32Array());
  audioFrames = 0; audioStatus.textContent = '连接中…'; setDiagnostic('正在连接本地服务');
  sessionStartedAt = Date.now();
  captureSessionId = `capture-${sessionStartedAt}-${++captureSessionSequence}`;
  if (!navigator.mediaDevices?.getUserMedia) {
    sessionLabel.textContent = '当前 App 不支持麦克风输入，请检查 macOS 麦克风权限。';
    startBtn.disabled = false;
    setSessionControls(false);
    setRuntime(false, '不可用');
    return;
  }
  socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  const sessionSocket = socket;
  let configuration = null;
  socket.onopen = async () => {
    try {
      setRuntime(false, '准备收音…'); stopBtn.disabled = false;
      setDiagnostic('正在准备所选识别语言，完成后开启麦克风');
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('识别语言准备超时，请检查模型状态')), 180000);
        configuration = { resolve: () => { clearTimeout(timer); resolve(); }, reject: error => { clearTimeout(timer); reject(error); } };
        socket.send(JSON.stringify({ type: 'config', source_language: sourceLanguage.value, target_language: targetLanguage.value, language_pair: sourceLanguage.value === 'auto' ? selectedLanguagePair : null, speaker_mode: speakerMode.value }));
      });
      configuration = null;
      if (socket !== sessionSocket || sessionSocket.readyState !== WebSocket.OPEN) return;
      const audio = { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true };
      if (inputDevice.value) audio.deviceId = { exact: inputDevice.value };
      let selectedStream;
      try {
        selectedStream = await navigator.mediaDevices.getUserMedia({ audio });
      } catch (error) {
        // Device IDs can change when macOS grants microphone permission. Retry
        // with the default input instead of ending the whole session.
        if (error.name !== 'OverconstrainedError' && error.name !== 'NotFoundError') throw error;
        selectedStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      }
      // Permission changes macOS device IDs and reveals their human-readable
      // names. Display the track actually opened, including a default fallback.
      if (socket !== sessionSocket || sessionSocket.readyState !== WebSocket.OPEN) {
        selectedStream.getTracks().forEach(track => track.stop()); return;
      }
      mediaStream = selectedStream;
      sessionStartedAt = Date.now();
      await loadDevices(mediaStream.getAudioTracks()[0]);
      if (socket !== sessionSocket || sessionSocket.readyState !== WebSocket.OPEN) return;
      audioContext = new AudioContext(); const source = audioContext.createMediaStreamSource(mediaStream); processor = audioContext.createScriptProcessor(4096, 1, 1);
      await audioContext.resume();
      processor.onaudioprocess = (event) => {
        if (socket.readyState !== WebSocket.OPEN) return;
        audioFrames += 1;
        if (audioFrames === 1 || audioFrames % 20 === 0) {
          if (queuedAudioMs <= 1500 && pendingAudio.length <= 16000) audioStatus.textContent = `已采集 ${audioFrames} 帧`;
          if (!lastCaptionAt) setDiagnostic('已收到音频，正在等待语音识别');
        }
        const pcm = downsample(event.inputBuffer.getChannelData(0), audioContext.sampleRate, 16000);
        updateInputLevel(pcm);
        // Send every short PCM frame and let the server apply the mode-specific
        // silence gate. Browser-side VAD can mistake quiet speech for noise,
        // especially during the first frames after microphone permission.
        queueAudioFrame(pcm);
      };
      const silentOutput = audioContext.createGain(); silentOutput.gain.value = 0;
      source.connect(processor); processor.connect(silentOutput); silentOutput.connect(audioContext.destination); stopBtn.disabled = false; setDiagnostic(`音频已开启：${sourceStatus.textContent}`); setRuntime(true, '运行中');
    } catch (error) { if (sessionSocket.readyState > WebSocket.OPEN) return; cleanupAudio(); audioStatus.textContent = '失败'; setDiagnostic(`音频输入失败：${error.message || '请检查系统麦克风权限'}`); if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) socket.close(); }
  };
  socket.onmessage = (message) => {
    const event = JSON.parse(message.data);
    if (event.type === 'caption') {
      const captionKey = `${event.original_text || ''}\u0000${event.translated_text || ''}`;
      if (runtimeMode === 'MOCK' && mockCaptionKeys.has(captionKey)) return;
      if (runtimeMode === 'MOCK') mockCaptionKeys.add(captionKey);
      upsertCaption(event);
      lastCaptionAt = Date.now();
      setDiagnostic(event.is_final ? '已识别并翻译字幕' : '已识别原文，翻译处理中');
      renderCaptions(); updateSummary();
    }
    if (event.type === 'status') setDiagnostic(event.message);
    if (event.type === 'configured') {
      if (event.language_pair) {
        recognitionLanguageStatus.textContent = `${event.language_pair.split('-').map(language => LANGUAGE_LABELS[language]).join(' / ')} · 自动识别`;
      } else updateRecognitionLanguage(event.asr_language || event.source_language);
      configuration?.resolve();
    }
    if (event.type === 'speaker_changed') {
      speakerMode.value = 'none'; speakerChoiceMade = true; updateSummary(); setDiagnostic(event.message);
      changeSpeakerBtn.disabled = sessionEnding; audioInFlight = false; sendPendingAudio();
    }
    if (event.type === 'audio_ack') { audioInFlight = false; sendPendingAudio(); }
    if (event.type === 'translation_status') {
      if (Number.isFinite(event.pending_translations)) pendingTranslations = event.pending_translations;
      translationStatus.textContent = `${statusText(event.state)}${pendingTranslations ? ` · 待处理 ${pendingTranslations} 段` : ''}`;
    }
    if (event.type === 'audio_status') {
      if (Number.isFinite(event.pending_translations)) pendingTranslations = event.pending_translations;
      if (Number.isFinite(event.queued_audio_ms)) queuedAudioMs = event.queued_audio_ms;
      if (Number.isFinite(event.queued_audio_ms)) audioStatus.textContent = event.queued_audio_ms > 1500 ? `识别积压 ${(event.queued_audio_ms / 1000).toFixed(1)} 秒 · 音频完整保留` : '音频接收正常 · 无跳过';
      if (event.state === 'rejected') setDiagnostic(event.message);
    }
    if (event.type === 'capture_paused') {
      stopCapture(); sessionEnding = true; setRuntime(false, '收音已暂停'); setDiagnostic(event.message); sendPendingAudio();
    }
    if (event.type === 'error') { setDiagnostic(`错误：${event.message}`); configuration?.reject(new Error(event.message)); }
    if (event.type === 'session_finished') setDiagnostic(event.rejected_samples ? '录音已收尾，但有音频未接收，请核对记录' : '本次发言已完整收尾，可导出记录');
  };
  socket.onclose = () => { configuration?.reject(new Error('录音准备已取消')); cleanupAudio(); setSessionControls(false); recognitionLanguageStatus.textContent = '未开始'; startBtn.disabled = runtimeMode !== 'LOCAL' || !modelsReady; stopBtn.disabled = true; setRuntime(false, '已停止'); };
  socket.onerror = () => { configuration?.reject(new Error('本地服务连接失败')); setDiagnostic('本地服务连接失败'); setRuntime(false, '连接失败'); };
}
function stopCapture() { if (processor) processor.disconnect(); if (audioContext) audioContext.close(); if (mediaStream) mediaStream.getTracks().forEach((track) => track.stop()); processor = null; audioContext = null; mediaStream = null; updateInputLevel(new Float32Array()); }
function cleanupAudio() { stopCapture(); activeInputLabel = ''; pendingAudio = new Float32Array(); audioInFlight = false; pendingBoundaryAudio = null; pendingSpeakerBoundary = false; sessionEnding = false; finishSent = false; }
function stopSession() {
  stopDemo();
  if (socket?.readyState === WebSocket.OPEN && !mediaStream && !processor && !pendingAudio.length && !audioInFlight && !audioFrames) {
    socket.close();
  } else if (socket?.readyState === WebSocket.OPEN) {
    stopCapture(); sessionEnding = true; stopBtn.disabled = true; changeSpeakerBtn.disabled = true;
    setRuntime(false, '正在收尾'); setDiagnostic('正在保留最后一段发言，请稍候…'); sendPendingAudio();
  } else if (socket?.readyState === WebSocket.CONNECTING) socket.close();
  else cleanupAudio();
}

function startSubtitleMode() {
  // Subtitle mode is a real transcript view. It never synthesizes sample
  // captions and can be entered before or during a meeting.
  setFloatingMode(!floatingMode);
  setDiagnostic(floatingMode ? '字幕模式已开启 · 等待真实字幕' : '已退出字幕模式');
}
function exportTranscript() {
  const text = transcriptParagraphs().map(row => `[${formatTime(row.start_ms)}] ${speakerLabel(row.speaker_id)}\n${row.original_text}\n${row.translated_text || ''}`).join('\n\n') || '暂无字幕';
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
  upsertCaption(event);
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
    if (!response.ok || (!result.ok && !result.requires_user)) throw new Error(result.message || result.detail || '操作失败');
    await checkOllama();
    systemNotice.textContent = result.message || '操作完成';
    systemNotice.className = result.requires_user ? 'system-notice warn' : 'system-notice good';
  } catch (error) {
    systemNotice.className = 'system-notice warn';
    systemNotice.textContent = `操作未完成：${error.message}`;
  } finally { button.disabled = false; }
}
startBtn.addEventListener('click', startSession);
stopBtn.addEventListener('click', stopSession);
demoBtn?.addEventListener('click', startSubtitleMode);
clearBtn.addEventListener('click', () => { stopDemo(); captionRows = []; followCaptions = true; latestBtn.hidden = true; mockCaptionKeys.clear(); renderCaptions(); updateSummary(); });
captions.addEventListener('scroll', () => {
  followCaptions = captions.scrollHeight - captions.clientHeight - captions.scrollTop < 48;
  latestBtn.hidden = followCaptions || !captionRows.length;
}, {passive: true});
latestBtn.addEventListener('click', returnToLatest);
changeSpeakerBtn.addEventListener('click', requestSpeakerChange);
exportBtn.addEventListener('click', exportTranscript);
floatingBtn?.addEventListener('click', () => setFloatingMode(!floatingMode));
interfaceLanguage?.addEventListener('change', () => setInterfaceLanguage(interfaceLanguage.value));
captionDisplayMode?.addEventListener('change', () => { renderCaptions(); });
tipsBtn?.addEventListener('click', () => toggleModal(tipsModal, true));
settingsBtn?.addEventListener('click', openSettings);
closeTipsBtn?.addEventListener('click', closeTips);
continueTipsBtn?.addEventListener('click', async () => { if (await closeTips()) await openSettings(); });
closeSettingsBtn?.addEventListener('click', () => toggleModal(settingsModal, false));
checkOllamaBtn?.addEventListener('click', checkOllama);
installOllamaBtn?.addEventListener('click', () => runSystemAction(installOllamaBtn, '/system/install', {}, '正在准备安装 Ollama…'));
upgradeOllamaBtn?.addEventListener('click', () => runSystemAction(upgradeOllamaBtn, '/system/upgrade', {}, '正在尝试升级本地翻译引擎…'));
pullModelBtn?.addEventListener('click', () => runSystemAction(pullModelBtn, '/system/pull-model', { model: recommendedModelStatus.textContent }, '正在下载推荐翻译模型…'));
saveSettingsBtn?.addEventListener('click', saveModelDirectory);
asrEngine?.addEventListener('change', checkAsrModel);
downloadAsrBtn?.addEventListener('click', () => runSystemAction(downloadAsrBtn, '/system/download-asr', {engine: asrEngine.value || 'whisper'}, '正在下载语音识别模型…').then(checkAsrModel));
chooseModelDirectoryBtn?.addEventListener('click', () => {
  if (window.webkit?.messageHandlers?.native) window.webkit.messageHandlers.native.postMessage({ type: 'choose_model_directory' });
  else modelDirectory?.focus();
});
sourceLanguage.addEventListener('change', () => { ensureDifferentLanguages('source'); updateSummary(); });
targetLanguage.addEventListener('change', () => { ensureDifferentLanguages('target'); updateSummary(); });
speakerMode.addEventListener('change', () => { speakerChoiceMade = true; updateSummary(); });
inputDevice.addEventListener('change', updateSummary);
navigator.mediaDevices?.addEventListener?.('devicechange', () => loadDevices(mediaStream?.getAudioTracks()[0]));
swapLanguagesBtn.addEventListener('click', swapLanguages);
directionButtons.forEach(button => button.addEventListener('click', () => setDirection(button.dataset.source, button.dataset.target)));
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  if (!settingsModal.hidden) toggleModal(settingsModal, false);
  else if (!tipsModal.hidden) closeTips();
  else if (floatingMode) setFloatingMode(false);
});
try { if (interfaceLanguage) interfaceLanguage.value = localStorage.getItem('interfaceLanguage') || 'auto'; } catch { if (interfaceLanguage) interfaceLanguage.value = 'auto'; }
applyInterfaceLanguage();
modeStatus.textContent = uiText('runtime.idle'); modeBadge.textContent = uiText('mode.local'); startBtn.disabled = true;
renderCaptions(); updateSummary(); loadDevices(); loadPreferences(); checkOllama();
if (serviceAddress) serviceAddress.textContent = location.host;
fetch('/health').then(response => response.json()).then(updateHealth).catch(() => { setDiagnostic('本地服务未连接，可先检查 App 状态'); });
setInterval(() => { fetch('/health').then(response => response.json()).then(updateHealth).catch(() => {}); }, 3000);
setInterval(() => {
  if (!socket || socket.readyState !== WebSocket.OPEN || !audioFrames || lastCaptionAt) return;
  if (sessionStartedAt && Date.now() - sessionStartedAt > 7000) setDiagnostic(lastInputRms < .003 ? '输入静音或音量较低，请检查所选麦克风；线上会议需配置回环音频' : '收到声音但尚无可靠字幕，请检查输入设备和源语言');
}, 2000);
