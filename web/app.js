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
const startupIntro = document.querySelector('#startupIntro');
const startupProgress = document.querySelector('#startupProgress');
const startupMessage = document.querySelector('#startupMessage');
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
const asrModel = document.querySelector('#asrModel');
const asrServiceUrl = document.querySelector('#asrServiceUrl');
const translationEngine = document.querySelector('#translationEngine');
const translationModel = document.querySelector('#translationModel');
const translationServiceUrl = document.querySelector('#translationServiceUrl');
const translationModelStatus = document.querySelector('#translationModelStatus');
const refreshModelsBtn = document.querySelector('#refreshModelsBtn');
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
const sourceLanguageButtons = [...document.querySelectorAll('.source-language-button')];

let socket;
let audioContext;
let mediaStream;
let activeInputLabel = '';
let pendingAudio = new Float32Array();
let latestCaptureAt = 0;
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
const incompleteSessions = new Set();
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
let interfaceChoiceMade = false;
let modelSelectionRevision = {asr: 0, translation: 0};
const SERVICE_DEFAULT_URLS = {ollama: 'http://127.0.0.1:11434', llama: 'http://127.0.0.1:9931'};
const serviceCapacities = new Map();
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
    'status.localRun': '本地运行', 'status.liveText': '实时文字', 'intro.title': '把会议内容留在本机。', 'intro.description': '实时识别、区分说话人，并生成中日、中英、英日双向字幕。', 'transcript.segments': '段发言', 'tips.kicker': '使用提示', 'tips.title': '三步开始本地会议翻译', 'tips.lead': '所有音频和模型都留在这台 Mac 上。字幕模式只显示已经收到的真实原文和译文，不生成模拟内容。', 'tips.audioTitle': '选音频', 'tips.audioBody': '麦克风用于现场会议；腾讯会议、Teams 和网页视频请选择 BlackHole、Loopback 等系统回环设备。', 'tips.modelTitle': '等模型就绪', 'tips.modelBody': '顶部显示冷启动进度。看到“模型可用 · 热启动”后再开始会议。', 'tips.floatingTitle': '需要时开浮窗', 'tips.floatingBody': '点击“字幕模式”，字幕会置顶、半透明并可拖动、缩放到会议窗口空白处。', 'tips.remember': '以后不再提醒', 'actions.later': '稍后再看', 'actions.setup': '开始设置', 'actions.close': '关闭', 'settings.kicker': '本机环境', 'settings.title': '模型与 Ollama 设置', 'settings.ollamaInstall': 'Ollama 安装', 'settings.version': '当前版本', 'settings.recommendedModel': '推荐翻译模型', 'settings.modelStatus': '模型状态', 'settings.asrEngine': '语音转文字引擎', 'settings.prepareAsr': '准备语音模型', 'settings.captionContent': '字幕显示内容', 'settings.bilingual': '双语对照：源与译', 'settings.sourceOnly': '仅显示源文', 'settings.translationOnly': '仅显示译文', 'settings.captionHint': '中日：中文左、日文右；中英：中文左、英文右；英日：英文左、日文右。“源 / 译”随实际发言切换。', 'settings.modelDirectory': '模型保存目录', 'settings.chooseDirectory': '选择目录', 'settings.ollamaDirectory': '使用 Ollama 当前目录', 'settings.directoryHint': '默认使用 Ollama 当前模型目录，可随时自定义。更改后重新检测，保存并重启后加载；现有文件不会自动迁移。Ollama / llama.app 的模型仍由对应服务管理。', 'settings.onlineAudio': '在线会议 / 网页视频音频', 'settings.onlineAudioHint': '系统音频捕获需要 macOS 音频回环设备。安装 BlackHole 或 Loopback 后，在设置的“音频输入”中选择对应设备；应用不会把会议音频上传到网络。', 'settings.recheck': '重新检查', 'settings.installOllama': '安装 Ollama', 'settings.upgradeOllama': '升级 Ollama', 'settings.installModel': '安装推荐模型', 'settings.save': '保存设置', 'footer.config': '文字模式 · M3 / 16G 配置', 'footer.service': '服务地址',
    'controls.ariaLabel': '会议输入设置', 'controls.audioInput': '音频输入', 'controls.defaultMic': '默认麦克风（授权后显示名称）', 'controls.sourceLanguage': '源语言', 'controls.targetLanguage': '目标语言', 'controls.speaker': '说话人',
    'speaker.manual': '手动换人', 'speaker.autoTest': '自动分人（测试）', 'direction.ariaLabel': '翻译方向快捷设置', 'direction.sourceLanguage': '源语言', 'direction.eyebrow': 'TRANSLATION DIRECTIONS', 'direction.title': '选择会议语言', 'direction.hint': '双方轮流发言，自动识别与互译',
    'transcript.eyebrow': 'LIVE TRANSCRIPT', 'transcript.title': '发言记录', 'transcript.footnote': '同一发言人连续记录 · 向上滚动查看历史，回到底部继续跟随', 'session.waitingAudio': '等待音频输入', 'status.eyebrow': 'SESSION', 'status.title': '当前状态', 'status.inputSource': '输入来源', 'status.inputLevel': '输入电平', 'status.recognitionLanguage': '识别语言', 'status.direction': '方向', 'status.speakerMode': '说话人模式', 'status.runMode': '运行模式', 'status.asr': '语音识别', 'status.ollama': '翻译引擎', 'status.translationModel': '翻译模型', 'status.translation': '翻译状态', 'status.audio': '音频链路', 'status.diagnostic': '诊断',
    'status.loading': '加载中', 'status.ready': '已就绪', 'status.running': '运行中', 'status.processing': '推理中', 'status.configured': '已配置', 'status.offline': '未连接', 'status.missing': '缺少模型', 'status.error': '错误', 'status.mock': '演示', 'status.unknown': '未知',
    'language.locked': '已锁定{language}', 'language.autoDetected': '自动识别', 'language.zhName': '中文', 'language.jaName': '日语', 'language.enName': '英语',
    'caption.waiting': '等待实时字幕', 'caption.emptyHint': '选择麦克风或 BlackHole 回环设备后开始会议。', 'caption.translationPending': '翻译处理中…', 'caption.translationUpdating': '译文更新中',
    'runtime.idle': '待机', 'runtime.connecting': '连接中…', 'runtime.preparing': '准备收音…', 'runtime.running': '运行中', 'runtime.stopped': '已停止', 'runtime.unavailable': '不可用', 'runtime.finishing': '正在收尾', 'runtime.paused': '收音已暂停',
  },
  ja: {
    'brand.name': 'LOCAL INTERPRETER', 'nav.workspace': 'MEETING WORKSPACE', 'nav.liveMeeting': 'リアルタイム会議', 'mode.local': 'ローカル', 'mode.demo': 'デモ', 'language.interface': '表示言語', 'language.auto': '自動', 'language.zh': '中文', 'language.ja': '日本語', 'language.en': 'English', 'language.autoDetect': '自動認識', 'language.zhSimplified': '中国語（簡体字）',
    'actions.guide': '使い方', 'actions.settings': 'ローカル設定', 'actions.subtitleMode': '字幕モード', 'actions.exitSubtitleMode': '字幕モードを終了', 'actions.export': '記録を書き出す', 'actions.startAudio': '音声入力を開始', 'actions.stop': '停止', 'actions.latest': '最新へ ↓', 'actions.clear': 'クリア', 'actions.floating': '字幕フロート', 'actions.exitFloating': 'フロートを終了',
    'status.localRun': 'ローカル実行', 'status.liveText': 'リアルタイム文字', 'intro.title': '会議の内容をこの Mac に保存。', 'intro.description': '発話を認識し、話者を分けて中日・中英・英日を双方向に字幕化します。', 'transcript.segments': '発話', 'tips.kicker': '使い方', 'tips.title': '3 ステップでローカル会議翻訳', 'tips.lead': '音声とモデルはこの Mac に保存されます。字幕モードは受信した実際の原文と訳文だけを表示します。', 'tips.audioTitle': '音声を選択', 'tips.audioBody': '現地会議はマイク、Teams・Tencent Meeting・Web 動画は BlackHole や Loopback を選択します。', 'tips.modelTitle': 'モデルを待つ', 'tips.modelBody': '上部にコールドスタートの進捗が表示されます。「モデル準備完了 · ウォーム」を確認してから開始します。', 'tips.floatingTitle': 'フロートを使う', 'tips.floatingBody': '字幕モードは最前面・半透明で、会議画面の空き場所へ移動できます。', 'tips.remember': '次回から表示しない', 'actions.later': '後で', 'actions.setup': '設定を開始', 'actions.close': '閉じる', 'settings.kicker': 'ローカル環境', 'settings.title': 'モデルと Ollama の設定', 'settings.ollamaInstall': 'Ollama のインストール', 'settings.version': '現在のバージョン', 'settings.recommendedModel': '推奨翻訳モデル', 'settings.modelStatus': 'モデル状態', 'settings.asrEngine': '音声認識エンジン', 'settings.prepareAsr': '音声モデルを準備', 'settings.captionContent': '字幕の表示内容', 'settings.bilingual': '対訳：原文と訳文', 'settings.sourceOnly': '原文のみ', 'settings.translationOnly': '訳文のみ', 'settings.captionHint': '中日：中国語を左、日本語を右。中英：中国語を左、英語を右。英日：英語を左、日本語を右。原文と訳文の表示は発話ごとに切り替わります。', 'settings.modelDirectory': 'モデル保存先', 'settings.chooseDirectory': 'フォルダを選択', 'settings.ollamaDirectory': 'Ollama の保存先を使用', 'settings.directoryHint': '初期値は Ollama のモデル保存先です。変更後に再検出し、保存・再起動後に読み込みます。ファイルは自動移動しません。サービスのモデルは各 App が管理します。', 'settings.onlineAudio': 'オンライン会議 / Web 動画の音声', 'settings.onlineAudioHint': 'システム音声の取り込みには macOS のループバックデバイスが必要です。BlackHole または Loopback をインストールし、設定の音声入力として選択します。音声はネットワークへ送信されません。', 'settings.recheck': '再チェック', 'settings.installOllama': 'Ollama をインストール', 'settings.upgradeOllama': 'Ollama を更新', 'settings.installModel': '推奨モデルをインストール', 'settings.save': '設定を保存', 'footer.config': '文字モード · M3 / 16G', 'footer.service': 'サービス',
    'controls.ariaLabel': '会議入力設定', 'controls.audioInput': '音声入力', 'controls.defaultMic': 'デフォルトマイク（許可後に表示）', 'controls.sourceLanguage': '原言語', 'controls.targetLanguage': '翻訳先', 'controls.speaker': '話者', 'speaker.manual': '手動で話者変更', 'speaker.autoTest': '自動話者分離（テスト）',
    'direction.ariaLabel': '翻訳方向のクイック設定', 'direction.sourceLanguage': '原言語', 'direction.eyebrow': 'TRANSLATION DIRECTIONS', 'direction.title': '会議の言語を選択', 'direction.hint': '交互に話す会議を自動認識して翻訳', 'transcript.eyebrow': 'LIVE TRANSCRIPT', 'transcript.title': '発話記録', 'transcript.footnote': '同じ話者を連続表示 · 上へスクロールして履歴を確認し、最下部で追従', 'session.waitingAudio': '音声入力を待機中', 'status.eyebrow': 'SESSION', 'status.title': '現在の状態', 'status.inputSource': '音声入力', 'status.inputLevel': '入力レベル', 'status.recognitionLanguage': '認識言語', 'status.direction': '方向', 'status.speakerMode': '話者モード', 'status.runMode': '実行モード', 'status.asr': '音声認識', 'status.ollama': '翻訳エンジン', 'status.translationModel': '翻訳モデル', 'status.translation': '翻訳状態', 'status.audio': '音声経路', 'status.diagnostic': '診断',
    'status.loading': '読み込み中', 'status.ready': '準備完了', 'status.running': '実行中', 'status.processing': '推論中', 'status.configured': '設定済み', 'status.offline': '未接続', 'status.missing': 'モデル不足', 'status.error': 'エラー', 'status.mock': 'デモ', 'status.unknown': '不明', 'language.locked': '{language} に固定', 'language.autoDetected': '自動認識', 'language.zhName': '中国語', 'language.jaName': '日本語', 'language.enName': '英語', 'caption.waiting': 'リアルタイム字幕を待機中', 'caption.emptyHint': 'マイクまたは BlackHole のループバックを選択して会議を開始します。', 'caption.translationPending': '翻訳中…', 'caption.translationUpdating': '翻訳を更新中', 'runtime.idle': '待機中', 'runtime.connecting': '接続中…', 'runtime.preparing': '音声入力を準備中…', 'runtime.running': '実行中', 'runtime.stopped': '停止', 'runtime.unavailable': '利用不可', 'runtime.finishing': '終了処理中', 'runtime.paused': '音声入力を一時停止',
  },
  en: {
    'brand.name': 'LOCAL INTERPRETER', 'nav.workspace': 'MEETING WORKSPACE', 'nav.liveMeeting': 'Live meeting', 'mode.local': 'Local', 'mode.demo': 'Demo', 'language.interface': 'Interface language', 'language.auto': 'Auto', 'language.zh': '中文', 'language.ja': '日本語', 'language.en': 'English', 'language.autoDetect': 'Auto detect', 'language.zhSimplified': 'Chinese (Simplified)',
    'actions.guide': 'Guide', 'actions.settings': 'Local settings', 'actions.subtitleMode': 'Subtitle mode', 'actions.exitSubtitleMode': 'Exit subtitle mode', 'actions.export': 'Export record', 'actions.startAudio': 'Start audio input', 'actions.stop': 'Stop', 'actions.latest': 'Back to latest ↓', 'actions.clear': 'Clear', 'actions.floating': 'Floating captions', 'actions.exitFloating': 'Exit floating mode',
    'status.localRun': 'Running locally', 'status.liveText': 'Live text', 'intro.title': 'Keep the meeting on this Mac.', 'intro.description': 'Recognize speech, separate speakers, and create two-way Chinese, Japanese, and English captions.', 'transcript.segments': 'segments', 'tips.kicker': 'Tips', 'tips.title': 'Start local meeting translation in three steps', 'tips.lead': 'Audio and models stay on this Mac. Subtitle mode only shows received source and translated text; it never invents sample output.', 'tips.audioTitle': 'Choose audio', 'tips.audioBody': 'Use a microphone for in-room meetings; choose BlackHole or Loopback for Tencent Meeting, Teams, and web video.', 'tips.modelTitle': 'Wait for models', 'tips.modelBody': 'Cold-start progress appears at the top. Start when you see “Models ready · warm”.', 'tips.floatingTitle': 'Use floating captions', 'tips.floatingBody': 'Subtitle mode stays on top, remains translucent, and can be moved over an empty area of the meeting window.', 'tips.remember': 'Do not show again', 'actions.later': 'Later', 'actions.setup': 'Start setup', 'actions.close': 'Close', 'settings.kicker': 'Local environment', 'settings.title': 'Model and Ollama settings', 'settings.ollamaInstall': 'Ollama installation', 'settings.version': 'Current version', 'settings.recommendedModel': 'Recommended translation model', 'settings.modelStatus': 'Model status', 'settings.asrEngine': 'Speech-to-text engine', 'settings.prepareAsr': 'Prepare speech model', 'settings.captionContent': 'Caption display', 'settings.bilingual': 'Bilingual: source and translation', 'settings.sourceOnly': 'Source only', 'settings.translationOnly': 'Translation only', 'settings.captionHint': 'Chinese/Japanese: Chinese left, Japanese right. Chinese/English: Chinese left, English right. English/Japanese: English left, Japanese right. Source and translation markers follow the speaker.', 'settings.modelDirectory': 'Model directory', 'settings.chooseDirectory': 'Choose folder', 'settings.ollamaDirectory': 'Use Ollama folder', 'settings.directoryHint': 'Defaults to the Ollama model folder; choose any local folder. Changes rescan files; save and restart to load. Files are not moved. Ollama / llama.app manage their own models.', 'settings.onlineAudio': 'Online meeting / web video audio', 'settings.onlineAudioHint': 'System audio capture requires a macOS loopback device. Install BlackHole or Loopback, then choose it under Audio input in settings. Audio stays local and is not uploaded.', 'settings.recheck': 'Check again', 'settings.installOllama': 'Install Ollama', 'settings.upgradeOllama': 'Update Ollama', 'settings.installModel': 'Install recommended model', 'settings.save': 'Save settings', 'footer.config': 'Text mode · M3 / 16G', 'footer.service': 'Service',
    'controls.ariaLabel': 'Meeting input settings', 'controls.audioInput': 'Audio input', 'controls.defaultMic': 'Default microphone (name appears after permission)', 'controls.sourceLanguage': 'Source language', 'controls.targetLanguage': 'Target language', 'controls.speaker': 'Speaker', 'speaker.manual': 'Manual speaker change', 'speaker.autoTest': 'Automatic speaker split (test)',
    'direction.ariaLabel': 'Quick translation direction settings', 'direction.sourceLanguage': 'Source language', 'direction.eyebrow': 'TRANSLATION DIRECTIONS', 'direction.title': 'Choose meeting languages', 'direction.hint': 'Auto-detect and translate alternating speakers', 'transcript.eyebrow': 'LIVE TRANSCRIPT', 'transcript.title': 'Transcript', 'transcript.footnote': 'Keep consecutive speech together · scroll up for history and return to the bottom to follow', 'session.waitingAudio': 'Waiting for audio input', 'status.eyebrow': 'SESSION', 'status.title': 'Current status', 'status.inputSource': 'Audio input', 'status.inputLevel': 'Input level', 'status.recognitionLanguage': 'Recognition language', 'status.direction': 'Direction', 'status.speakerMode': 'Speaker mode', 'status.runMode': 'Run mode', 'status.asr': 'Speech recognition', 'status.ollama': 'Translation engine', 'status.translationModel': 'Translation model', 'status.translation': 'Translation status', 'status.audio': 'Audio path', 'status.diagnostic': 'Diagnostics',
    'status.loading': 'Loading', 'status.ready': 'Ready', 'status.running': 'Running', 'status.processing': 'Processing', 'status.configured': 'Configured', 'status.offline': 'Offline', 'status.missing': 'Model missing', 'status.error': 'Error', 'status.mock': 'Demo', 'status.unknown': 'Unknown', 'language.locked': 'Locked to {language}', 'language.autoDetected': 'Auto-detect', 'language.zhName': 'Chinese', 'language.jaName': 'Japanese', 'language.enName': 'English', 'caption.waiting': 'Waiting for live captions', 'caption.emptyHint': 'Choose a microphone or BlackHole loopback device to start the meeting.', 'caption.translationPending': 'Translation pending…', 'caption.translationUpdating': 'Updating translation', 'runtime.idle': 'Idle', 'runtime.connecting': 'Connecting…', 'runtime.preparing': 'Preparing audio…', 'runtime.running': 'Running', 'runtime.stopped': 'Stopped', 'runtime.unavailable': 'Unavailable', 'runtime.finishing': 'Finishing', 'runtime.paused': 'Audio paused',
  },
};

Object.entries({
  zh: {'models.speech': '语音识别 · 声音转文字', 'models.translation': '文字翻译 · 中日英互译', 'models.service': '运行服务', 'models.address': '本机服务地址', 'models.model': '模型', 'models.speechHint': 'Qwen3-ASR 通过所选服务识别原文；另一侧独立选择翻译模型。', 'models.translationHint': '只列出可用于文字生成的模型。识别和翻译可使用不同服务。', 'models.restart': '选择后保存并重新打开 App 生效；刷新列表不会加载或下载模型。', 'models.refresh': '刷新模型列表'},
  ja: {'models.speech': '音声認識 · 音声から文字へ', 'models.translation': '翻訳 · 中日英の相互翻訳', 'models.service': '実行サービス', 'models.address': 'ローカルサービスのアドレス', 'models.model': 'モデル', 'models.speechHint': 'Qwen3-ASR は原文を認識します。翻訳モデルは別に選択します。', 'models.translationHint': '文字生成モデルを表示します。認識と翻訳には別々のサービスを使えます。', 'models.restart': '保存後に App を再起動してください。更新はモデルを読み込み・ダウンロードしません。', 'models.refresh': 'モデル一覧を更新'},
  en: {'models.speech': 'Speech recognition · audio to text', 'models.translation': 'Translation · Chinese, Japanese, English', 'models.service': 'Model service', 'models.address': 'Local service address', 'models.model': 'Model', 'models.speechHint': 'Qwen3-ASR recognizes the source speech. Select a translation model separately.', 'models.translationHint': 'Lists text generation models. Recognition and translation can use different services.', 'models.restart': 'Save and reopen the App to apply. Refreshing does not load or download models.', 'models.refresh': 'Refresh model lists'},
}).forEach(([language, strings]) => Object.assign(UI_TEXT[language], strings));
Object.assign(UI_TEXT.zh, {'models.apple': 'Apple SpeechAnalyzer · Apple 本机语音识别', 'settings.title': '模型与服务设置', 'models.ollamaTools': 'Ollama 安装与下载（可选）', 'models.whisper': 'Whisper · 内置本地识别', 'models.sensevoice': 'SenseVoice · 内置本地识别', 'models.nllb': 'NLLB · 内置本地翻译'});
Object.assign(UI_TEXT.ja, {'models.apple': 'Apple SpeechAnalyzer · Apple オンデバイス音声認識', 'settings.title': 'モデルとサービスの設定', 'models.ollamaTools': 'Ollama のインストール・ダウンロード（任意）', 'models.whisper': 'Whisper · 内蔵音声認識', 'models.sensevoice': 'SenseVoice · 内蔵音声認識', 'models.nllb': 'NLLB · 内蔵翻訳'});
Object.assign(UI_TEXT.en, {'models.apple': 'Apple SpeechAnalyzer · on-device recognition', 'settings.title': 'Models and services', 'models.ollamaTools': 'Ollama installation and downloads (optional)', 'models.whisper': 'Whisper · built-in recognition', 'models.sensevoice': 'SenseVoice · built-in recognition', 'models.nllb': 'NLLB · built-in translation'});
UI_TEXT.zh['settings.directoryHint'] = '默认使用 Ollama 当前模型目录，可随时自定义。更改后重新检测，保存并重启后加载；现有文件不会自动迁移。Ollama / llama.app 的模型仍由对应服务管理。';
UI_TEXT.ja['settings.directoryHint'] = '初期値は Ollama のモデル保存先です。変更後に再検出し、保存・再起動後に読み込みます。ファイルは自動移動しません。サービスのモデルは各 App が管理します。';
UI_TEXT.en['settings.directoryHint'] = 'Defaults to the Ollama model folder; choose any local folder. Changes rescan files; save and restart to load. Files are not moved. Ollama / llama.app manage their own models.';

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
  document.querySelectorAll('.status-item dt').forEach(element => {
    element.title = element.querySelector('.status-label-text')?.textContent || element.title;
  });
  if (interfaceLanguage) interfaceLanguage.setAttribute?.('aria-label', uiText('language.interface'));
  updateAsrHint();
  if (asrEngine.value === 'apple' && lastAppleInventory) renderAppleAssetState(lastAppleInventory);
  updateCaptionHeaders(); updateSummary(); renderCaptions();
  if (lastHealth) updateHealth(lastHealth);
}
function setInterfaceLanguage(value) {
  const next = UI_TEXT[value] || value === 'auto' ? value : 'auto';
  try { localStorage.setItem('interfaceLanguage', next); } catch {}
  if (interfaceLanguage) interfaceLanguage.value = next;
  interfaceChoiceMade = true;
  applyInterfaceLanguage();
  fetch('/preferences', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({interface_language: next})}).then(response => {
      if (!response.ok) throw new Error('preference save failed');
    }).catch(() => setDiagnostic(localized('界面语言保存失败，请重试', '表示言語を保存できませんでした', 'Could not save interface language; please retry')));
}

function localized(zh, ja, en) { return ({zh, ja, en})[activeInterfaceLanguage()]; }

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
  if (key === 'timeout') return localized('超时已跳过', 'タイムアウト・スキップ', 'Timed out · skipped');
  const labels = { loading: 'status.loading', ready: 'status.ready', running: 'status.running', processing: 'status.processing', configured: 'status.configured', offline: 'status.offline', missing: 'status.missing', error: 'status.error', mock: 'status.mock' };
  return uiText(labels[key] || 'status.unknown', String(value || uiText('status.unknown')));
}
function updateHealth(health) {
  lastHealth = health;
  runtimeMode = String(health.mode || 'mock').toUpperCase();
  const modeLabel = runtimeMode === 'LOCAL' ? uiText('mode.local') : uiText('mode.demo');
  modeStatus.textContent = modeLabel;
  modeBadge.textContent = modeLabel;
  const models = health.settings?.restart_required
    ? {...health.models, ready:false, stage:'restart', progress:0, message:localized('设置已保存，请完全退出并重新打开 App', '設定を保存しました。App を終了して再起動してください', 'Settings saved. Quit and reopen the App to load the new models.')}
    : health.models || {};
  const prepared = runtimeMode === 'LOCAL' && Boolean(models.ready);
  document.body.classList.toggle('conversation-ready', prepared);
  if (startupIntro) startupIntro.hidden = prepared;
  if (startupProgress) startupProgress.value = Math.max(0, Math.min(100, Number(models.progress || 0)));
  if (startupMessage) startupMessage.textContent = modelReadiness?.textContent || models.message || uiText('status.loading');
  const wasModelsReady = modelsReady;
  if (modelReadiness) {
    modelsReady = Boolean(models.ready);
    modelReadiness.textContent = runtimeMode === 'MOCK' ? `${uiText('status.mock')} · ${activeInterfaceLanguage() === 'en' ? 'no live model' : activeInterfaceLanguage() === 'ja' ? '実モデル未使用' : '不使用真实模型'}` : models.ready ? (activeInterfaceLanguage() === 'en' ? 'Models ready · warm' : activeInterfaceLanguage() === 'ja' ? 'モデル準備完了 · ウォーム' : '模型可用 · 热启动') : `${Math.round(Number(models.progress || 0))}% · ${models.message || (activeInterfaceLanguage() === 'en' ? 'Models not ready' : activeInterfaceLanguage() === 'ja' ? 'モデル未準備' : '模型未就绪')}`;
    modelReadiness.classList.toggle('ready', Boolean(models.ready));
    modelReadiness.classList.toggle('error', models.stage === 'error');
    if (startupMessage) startupMessage.textContent = modelReadiness.textContent;
  }
  startBtn.disabled = runtimeMode !== 'LOCAL' || !models.ready || Boolean(socket && socket.readyState <= WebSocket.OPEN) || Boolean(demoTimer);
  startBtn.title = runtimeMode !== 'LOCAL' ? '尚未连接真实模型，可先使用字幕模式' : !models.ready ? '模型未就绪，请先检查本地设置' : '';
  if (runtimeMode === 'LOCAL' && !models.ready && !demoTimer) setDiagnostic(models.message || (activeInterfaceLanguage() === 'en' ? 'Models are not connected; subtitle mode is available' : activeInterfaceLanguage() === 'ja' ? 'モデル未接続。字幕モードを利用できます' : '模型未连接，可先使用字幕模式'));
  if (runtimeMode === 'LOCAL' && models.ready && !wasModelsReady && !demoTimer && !(socket && socket.readyState <= WebSocket.OPEN)) setDiagnostic(models.message || (activeInterfaceLanguage() === 'en' ? 'Models ready; you can start the meeting' : activeInterfaceLanguage() === 'ja' ? 'モデル準備完了。会議を開始できます' : '模型已就绪，可开始会议'));
  const asrProvider = health.asr?.backend === 'ollama' ? 'Ollama · ' : health.asr?.backend === 'llama' ? 'llama.app · ' : '';
  asrStatus.textContent = health.settings?.restart_required
    ? `${localized('待重启加载', '再起動後に読み込み', 'Restart to load')} · ${formatModel(health.settings.asr_model)}`
    : `${asrProvider}${statusText(health.asr?.status)} · ${formatModel(health.asr?.model)}`;
  const speakerOption = speakerMode.querySelector('option[value="embedding"]');
  if (speakerOption) speakerOption.disabled = !health.speaker?.available;
  speakerMode.title = health.speaker?.message || '未连接声纹模型，可手动换人';
  if (health.speaker?.available && !speakerChoiceMade && !(socket && socket.readyState <= WebSocket.OPEN)) {
    speakerMode.value = 'embedding'; speakerChoiceMade = true; updateSummary();
  }
  if (health.translation?.service?.provider === 'llama') {
    const service = health.translation.service;
    ollamaStatus.textContent = `llama.app · ${statusText(service.reachable ? health.translation.status : 'offline')}`;
    ollamaModelStatus.textContent = `${statusText(service.model_present ? health.translation.status : 'missing')} · ${formatModel(health.translation.model)}`;
  } else if (!health.ollama?.configured) {
    ollamaStatus.textContent = localized('未启用', '無効', 'Disabled');
    ollamaModelStatus.textContent = localized('当前使用其他翻译后端', '別の翻訳エンジンを使用', 'Using another engine');
  } else if (!health.ollama.reachable) {
    ollamaStatus.textContent = localized('未启动 / 无法连接', '未起動 / 未接続', 'Offline');
    ollamaModelStatus.textContent = formatModel(health.translation?.model);
  } else if (!health.ollama.model_present) {
    ollamaStatus.textContent = localized('已启动', '起動済み', 'Online');
    ollamaModelStatus.textContent = `${statusText('missing')} · ${formatModel(health.translation?.model)}`;
  } else if (health.translation?.status === 'processing') {
    ollamaStatus.textContent = localized('模型推理中', '推論中', 'Processing');
    ollamaModelStatus.textContent = `${statusText('processing')} · ${formatModel(health.translation?.model)}`;
  } else if (health.ollama.model_loaded) {
    ollamaStatus.textContent = localized('模型运行中', '実行中', 'Running');
    ollamaModelStatus.textContent = `${statusText('running')} · ${formatModel(health.translation?.model)}`;
  } else {
    ollamaStatus.textContent = localized('等待调用', '待機中', 'Standby');
    ollamaModelStatus.textContent = `${localized('尚未加载', '未ロード', 'Not loaded')} · ${formatModel(health.translation?.model)}`;
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
    if (!interfaceChoiceMade && ['auto', 'zh', 'ja', 'en'].includes(settings.interface_language)) {
      interfaceLanguage.value = settings.interface_language;
      applyInterfaceLanguage();
    }
    rememberTips.checked = settings.show_tips === false;
    toggleModal(tipsModal, settings.show_tips !== false);
  } catch { toggleModal(tipsModal, true); }
}
async function openSettings() {
  toggleModal(settingsModal, true);
  try {
    const response = await fetch('/settings');
    const settings = await response.json();
    modelDirectory.value = settings.model_dir || settings.ollama_model_dir || '';
    modelDirectory.dataset.ollamaDirectory = settings.ollama_model_dir || '';
    asrEngine.value = settings.asr_engine || 'whisper';
    asrServiceUrl.value = settings.asr_url || SERVICE_DEFAULT_URLS[asrEngine.value] || '';
    translationEngine.value = settings.translation_backend || 'ollama';
    translationServiceUrl.value = settings.translation_url || SERVICE_DEFAULT_URLS[translationEngine.value] || '';
    asrModel.dataset.selected = settings.asr_model || '';
    translationModel.dataset.selected = settings.translation_model || '';
  } catch { setDiagnostic('无法读取本地设置'); }
  await refreshModelSelections();
  await checkOllama();
}
function fillModelChoices(select, models, preferred = '') {
  const ids = models.map(model => typeof model === 'string' ? model : model.id);
  const matches = preferred && !preferred.includes('/') ? ids.filter(id => id.split('/').at(-1) === preferred) : [];
  const selected = ids.includes(preferred) ? preferred : matches.length === 1 ? matches[0] : preferred || ids[0] || '';
  const choices = ids.includes(selected) || !selected ? ids : [selected, ...ids];
  select.innerHTML = choices.length ? choices.map(id => `<option value="${escapeHtml(id)}">${escapeHtml(id)}${ids.includes(id) ? '' : localized(' · 未检测到', ' · 未検出', ' · Not found')}</option>`).join('') : `<option value="">${localized('无可用模型', '利用可能なモデルなし', 'No compatible models')}</option>`;
  select.value = selected;
  select.dataset.selected = '';
}
let lastAppleInventory = null;
let applePreparationBusy = false;
function renderAppleAssetState(info) {
  lastAppleInventory = info;
  const states = (info.languages || []).map(row => `${languageDisplayLabel(row.language)} ${row.installed ? '✓' : row.status === 'downloading' ? '↓' : '○'}`).join(' · ');
  asrModelStatus.textContent = !info.available ? info.message || localized('当前系统不支持，需要 macOS 26+', 'macOS 26 以降が必要です', 'Requires macOS 26+')
    : `${states} · ${info.installed ? localized('资源已就绪 · 保存并重启后使用', '準備完了 · 保存して再起動', 'Assets ready · save and restart') : localized('请准备当前会议语言资源', '会議の言語データを準備してください', 'Prepare assets for this meeting pair')}`;
  downloadAsrBtn.disabled = applePreparationBusy || !info.available || Boolean(info.installed);
  downloadAsrBtn.textContent = applePreparationBusy ? localized('正在准备…', '準備中…', 'Preparing…') : info.installed ? localized('Apple 语言资源已就绪', 'Apple 言語データ準備完了', 'Apple language assets ready') : localized('准备 Apple 语言资源', 'Apple 言語データを準備', 'Prepare Apple language assets');
}
function updateAsrHint() {
  if (asrEngineHint) asrEngineHint.textContent = asrEngine.value === 'apple'
    ? localized('需要 macOS 26+。语言资源由 macOS 管理，不使用自定义模型目录。双语自动判别为实验功能；可用源语言按钮纠正。仅识别原文，翻译模型独立运行。', 'macOS 26 以降が必要です。言語データは macOS が管理し、指定フォルダは使用しません。2 言語の自動判定は実験機能です。原言語ボタンで修正できます。翻訳モデルは別途使用します。', 'Requires macOS 26+. macOS manages language assets outside the custom model folder. Bilingual detection is experimental; correct it with source-language buttons. Translation uses a separate model.')
    : uiText('models.speechHint');
}
async function prepareSpeechModel() {
  if (asrEngine.value !== 'apple') {
    await runSystemAction(downloadAsrBtn, '/system/download-asr', {engine: asrEngine.value || 'whisper', model: asrModel.value}, '正在下载所选语音识别模型…');
    return checkAsrModel();
  }
  if (applePreparationBusy) return;
  applePreparationBusy = true;
  const revision = modelSelectionRevision.asr;
  const languages = selectedLanguagePair.split('-');
  downloadAsrBtn.disabled = true;
  downloadAsrBtn.setAttribute?.('aria-busy', 'true');
  asrModelStatus.textContent = localized('macOS 正在准备语言资源，首次下载需要联网，请稍候…', 'macOS が言語データを準備中です。初回ダウンロードにはネット接続が必要です…', 'macOS is preparing language assets; the first download needs internet. Please wait…');
  try {
    const response = await fetch('/system/download-asr', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({engine:'apple',languages})});
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.message || result.detail || '准备失败');
    if (revision !== modelSelectionRevision.asr || asrEngine.value !== 'apple') return;
    applePreparationBusy = false;
    await checkAsrModel();
  } catch(error) {
    if (revision === modelSelectionRevision.asr && asrEngine.value === 'apple') {
      asrModelStatus.textContent = `${localized('语言资源未准备完成', '言語データの準備未完了', 'Language assets not ready')}: ${error.message}`;
      downloadAsrBtn.disabled = false;
    }
  } finally {
    applePreparationBusy = false;
    downloadAsrBtn.setAttribute?.('aria-busy', 'false');
  }
}
async function checkAsrModel() {
  return refreshModelSelection('asr');
}
async function refreshModelSelections() {
  await Promise.all([refreshModelSelection('asr'), refreshModelSelection('translation')]);
}
async function refreshModelSelection(role) {
  const speech = role === 'asr';
  const engine = speech ? asrEngine : translationEngine;
  const model = speech ? asrModel : translationModel;
  const address = speech ? asrServiceUrl : translationServiceUrl;
  const status = speech ? asrModelStatus : translationModelStatus;
  const provider = engine.value || (speech ? 'whisper' : 'ollama');
  const revision = ++modelSelectionRevision[role];
  if (speech) updateAsrHint();
  const remote = Boolean(SERVICE_DEFAULT_URLS[provider]);
  document.querySelector(speech ? '#asrServiceField' : '#translationServiceField').hidden = !remote;
  if (remote && !address.value) address.value = SERVICE_DEFAULT_URLS[provider];
  status.textContent = localized('正在检查模型…', 'モデルを確認中…', 'Checking models…');
  if (speech) {
    downloadAsrBtn.hidden = remote;
    downloadAsrBtn.disabled = true;
  }
  const preferred = model.dataset.selected || model.value || '';
  try {
    const response = await fetch(remote
      ? `/services/models?provider=${provider}&url=${encodeURIComponent(address.value)}`
      : `/system/models?engine=${provider}&model=${encodeURIComponent(preferred)}&model_dir=${encodeURIComponent(modelDirectory.value.trim())}&language_pair=${selectedLanguagePair}`);
    const info = await response.json();
    if (revision !== modelSelectionRevision[role]) return;
    if (!response.ok) throw new Error(info.detail || '无法获取模型');
    if (remote) {
      if (info.max_loaded_models) serviceCapacities.set(address.value.replace(/\/v1\/?$|\/$/g, ''), info.max_loaded_models);
      const choices = (info.models || []).filter(item => item[speech ? 'asr' : 'translation']);
      fillModelChoices(model, choices, preferred);
      status.textContent = !info.reachable ? localized('服务未连接，请启动对应 App', 'サービス未接続。App を起動してください', 'Service offline; start its App')
        : !choices.length ? localized('已连接，未发现适用模型；请在服务 App 中添加后刷新', '接続済み。対応モデルを App に追加して更新してください', 'Connected; add a compatible model in the service App and refresh')
        : choices.some(item => item.id === model.value) ? localized('模型已找到 · 保存并重启后加载', 'モデル検出 · 保存・再起動後に読み込み', 'Model found · loads after save and restart')
        : localized('所选模型未检测到，请重新选择', '選択モデルは未検出です', 'Selected model not found; choose another');
    } else if (provider === 'apple') {
      model.value = ''; model.dataset.selected = '';
      fillModelChoices(model, ['Apple SpeechAnalyzer'], 'Apple SpeechAnalyzer');
      renderAppleAssetState(info);
    } else {
      model.value = ''; model.dataset.selected = '';
      fillModelChoices(model, info.models || [info.model || (provider === 'nllb' ? 'facebook/nllb-200-distilled-600M' : 'mlx-community/whisper-medium-mlx-8bit')], provider === 'sensevoice' ? 'SenseVoice-Small' : info.model || '');
      status.textContent = info.installed ? localized('本地文件已找到 · 保存并重启后加载', 'ファイル検出 · 保存・再起動後に読み込み', 'Local files found · save and restart to load') : !info.path || activeInterfaceLanguage() !== 'zh' ? localized('所选目录内未找到模型，请检查路径或重新选择', '保存先のモデルが見つかりません。パスを確認してください', 'Model not found in this folder; check the path or selection') : info.message || '本地模型尚未准备好';
      if (speech) {
        downloadAsrBtn.disabled = Boolean(info.installed) || provider === 'sensevoice';
        downloadAsrBtn.textContent = info.installed ? localized('语音模型已就绪', '準備完了', 'Speech model ready') : provider === 'sensevoice' ? localized('请导入本地文件', 'ファイルを追加', 'Import local files') : localized('下载所选语音模型', '選択モデルをダウンロード', 'Download selected speech model');
      }
    }
  } catch (error) {
    if (revision !== modelSelectionRevision[role]) return;
    status.textContent = `${localized('检查失败', '確認失敗', 'Check failed')}: ${error.message}`;
  }
  updateModelCompatibility();
}
function updateModelCompatibility() {
  const notice = document.querySelector('#modelCompatibilityNotice');
  const root = value => value.replace(/\/v1\/?$|\/$/g, '');
  const same = asrEngine.value === 'llama' && translationEngine.value === 'llama' && root(asrServiceUrl.value) === root(translationServiceUrl.value);
  notice.hidden = !(same && asrModel.value && translationModel.value && asrModel.value !== translationModel.value && serviceCapacities.get(root(asrServiceUrl.value)) === 1);
  notice.textContent = localized('llama.app 当前仅能驻留 1 个模型。请使用不同服务，或在 llama.app 中允许两个模型同时运行，避免反复冷启动。', 'llama.app は現在 1 モデルのみ常駐可能です。別々のサービスを使うか、2 モデルの同時実行を有効にしてください。', 'llama.app currently keeps only one model loaded. Use separate services or allow two resident models to avoid repeated cold starts.');
}
function changeModelProvider(role) {
  const speech = role === 'asr';
  const provider = (speech ? asrEngine : translationEngine).value;
  const model = speech ? asrModel : translationModel;
  if (speech) lastAppleInventory = null;
  model.value = ''; model.dataset.selected = '';
  (speech ? asrServiceUrl : translationServiceUrl).value = SERVICE_DEFAULT_URLS[provider] || '';
  refreshModelSelection(role);
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
  const notice = document.querySelector('#modelSaveNotice');
  notice.hidden = false;
  try {
    const response = await fetch('/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model_dir: value, asr_engine: asrEngine.value || 'whisper',
      asr_model: asrModel.value, asr_url: asrServiceUrl.value, translation_backend: translationEngine.value || 'ollama', translation_model: translationModel.value, translation_url: translationServiceUrl.value }) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || '保存失败');
    let saved = localized('识别、翻译模型与目录已保存，重新打开 App 后生效', '認識・翻訳モデルと保存先を保存しました。App を再起動してください', 'Recognition, translation and directory saved. Reopen the App to apply.');
    if (result.settings?.model_dir_exists === false) saved += localized('。模型目录当前不可用，内置识别需连接磁盘或选择有效目录；服务模型使用其自身存储', '。保存先は現在利用できません。内蔵認識には有効な保存先が必要です。サービスモデルはサービス側で保存されます', ' The model folder is currently unavailable. Built-in recognition needs a valid folder; service models use their own storage.');
    setDiagnostic(saved);
    notice.textContent = saved; notice.className = 'model-save-notice good';
    if (systemNotice) { systemNotice.className = 'system-notice good'; systemNotice.textContent = saved; }
    // Status refresh is independent of the configuration already written.
    try {
      const health = await fetch('/health');
      if (health.ok) updateHealth(await health.json());
    } catch { /* Keep the verified save receipt visible until the next poll. */ }
  } catch (error) {
    notice.textContent = `${localized('保存失败', '保存失敗', 'Save failed')}: ${error.message}`; notice.className = 'model-save-notice warn';
    if (systemNotice) { systemNotice.className = 'system-notice warn'; systemNotice.textContent = `保存失败：${error.message}`; }
  } finally { saveSettingsBtn.disabled = false; }
}
window.__onModelDirectorySelected = async (path) => {
  if (!modelDirectory) return;
  modelDirectory.value = path;
  await refreshModelSelections();
};
modelDirectory?.addEventListener('change', refreshModelSelections);
document.querySelector('#useOllamaDirectoryBtn')?.addEventListener('click', async () => {
  const response = await fetch('/settings');
  const settings = await response.json();
  if (response.ok && settings.ollama_model_dir) await window.__onModelDirectorySelected(settings.ollama_model_dir);
});

function setSessionControls(active) {
  [inputDevice, sourceLanguage, targetLanguage, speakerMode, swapLanguagesBtn, asrEngine, asrModel, asrServiceUrl, translationEngine, translationModel, translationServiceUrl, saveSettingsBtn, refreshModelsBtn, modelDirectory, document.querySelector('#chooseModelDirectoryBtn'), document.querySelector('#useOllamaDirectoryBtn'), ...directionButtons].forEach(control => {
    control.disabled = active;
    control.title = active ? '停止音频后可更改设置' : '';
  });
  // Keep the quick source-language correction buttons usable during recording.
  sourceLanguageButtons.forEach(button => { button.disabled = false; button.title = ''; });
  if (demoBtn) demoBtn.disabled = false;
  changeSpeakerBtn.disabled = !active;
}
function updateRecognitionLanguage(language) {
  const name = language && language !== 'auto' ? languageDisplayLabel(language) : '';
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
  const direction = `${selectedLanguagePair.split('-').map(languageDisplayLabel).join(' ↔ ')} · ${localized('自动互译', '自動翻訳', 'Auto')}`;
  directionStatus.textContent = direction;
  directionPill.textContent = direction;
  speakerStatus.textContent = speakerMode.options[speakerMode.selectedIndex]?.textContent || '稍后区分';
  sourceStatus.textContent = activeInputLabel || inputDevice.options[inputDevice.selectedIndex]?.textContent || '未选择';
  directionButtons.forEach(button => {
    const selected = `${button.dataset.source}-${button.dataset.target}` === selectedLanguagePair;
    button.classList.toggle('selected', selected);
    button.setAttribute?.('aria-pressed', String(selected));
  });
  sourceLanguageButtons.forEach(button => {
    button.hidden = button.dataset.language !== 'auto' && !selectedLanguagePair.split('-').includes(button.dataset.language);
    const selected = button.dataset.language === (sourceLanguage.value || 'auto');
    button.classList.toggle('selected', selected);
    button.setAttribute?.('aria-pressed', String(selected));
  });
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
  const source = chunks.map(chunk => ({role: '源', text: chunk.original_text, language: chunk.source_language, skipped: chunk.skipped_stage === 'recognition'}));
  const translation = chunks.map(chunk => ({role: '译', text: chunk.translated_text, language: chunk.target_language, skipped: Boolean(chunk.skipped_stage)}));
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
  const mixed = new Set(parts.map(part => part.role)).size > 1;
  return parts.map((part, index) =>
    `<span class="caption-part" data-role="${part.role}" title="${part.role === '源' ? uiText('settings.sourceOnly') : uiText('settings.translationOnly')}">${index === 0 ? `<b class="caption-role ${mixed ? 'mixed-role' : part.role === '源' ? 'source-role' : 'translation-role'}">${mixed ? localized('源 / 译', '原文 / 訳文', 'Source / Translation') : part.role === '源' ? localized('源文', '原文', 'Source') : localized('译文', '訳文', 'Translation')}</b>` : ''}${escapeHtml(part.text || (part.skipped ? localized('超时已跳过', 'タイムアウト・スキップ', 'Timed out · skipped') : uiText('caption.translationPending')))}${part.skipped && part.text ? `<small class="caption-skipped">${localized('已结束等待', '待機終了', 'Wait ended')}</small>` : ''} </span>`
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
  sourceLanguageButtons.forEach(button => {
    const selected = button.dataset.language === 'auto';
    button.classList.toggle('selected', selected);
    button.setAttribute?.('aria-pressed', String(selected));
  });
  updateSummary(); renderCaptions();
}
function setSourceLanguage(language) {
  const pair = selectedLanguagePair.split('-');
  if (language !== 'auto' && !pair.includes(language)) return;
  sourceLanguage.value = language;
  targetLanguage.value = language === 'auto' ? pair[1] : pair.find(item => item !== language);
  updateSummary();
  if (socket?.readyState === WebSocket.OPEN) {
    // The server applies this boundary after audio it has already accepted.
    socket.send(JSON.stringify({type: 'source_language', source_language: language}));
    setDiagnostic(localized('正在切换识别语言…', '認識言語を切り替え中…', 'Switching recognition language…'));
  }
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
    if (previous.skipped_stage && !event.skipped_stage && event.end_ms <= previous.end_ms) return;
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
    const sameTurn = paragraph && (paragraph.paragraph_id && row.paragraph_id
      ? paragraph.paragraph_id === row.paragraph_id
      : paragraph.speaker_id === row.speaker_id || paragraph.speaker_id === 'SPEAKER_PENDING' || row.speaker_id === 'SPEAKER_PENDING');
    const rowPair = row.language_pair || pairForLanguages(row.source_language, row.target_language);
    const paragraphPair = paragraph && (paragraph.language_pair || pairForLanguages(paragraph.source_language, paragraph.target_language));
    if (!paragraph || !sameTurn || paragraph.session_id !== row.session_id || paragraphPair !== rowPair) {
      paragraph = {...row, original_text: '', translated_text: '', chunks: []};
      paragraphs.push(paragraph);
    }
    if (row.speaker_id !== 'SPEAKER_PENDING') paragraph.speaker_id = row.speaker_id;
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
  const capturedAt = (latestCaptureAt || Date.now()) - (pendingAudio.length + (pendingBoundaryAudio?.length || 0) + pcm.length) / 16;
  socket.send(JSON.stringify({type:'audio',session_id:captureSessionId,audio_base64:encodePcm(pcm),sample_rate:16000,channels:1,source:sourceType,captured_at_ms:capturedAt}));
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
  latestCaptureAt = Date.now();
  if (pendingAudio.length + pcm.length > 16000 * 4) {
    incompleteSessions.add(captureSessionId);
    pendingAudio = pendingAudio.slice(-16000);
    if (pendingBoundaryAudio?.length) pendingBoundaryAudio = null;
    setDiagnostic(localized('音频传送超时，已跳过旧音频，保留最新发言', '音声転送が遅れたため古い音声をスキップ', 'Audio transfer stalled; skipped old audio and kept latest speech'));
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
  if (!['auto', 'zh', 'ja', 'en'].includes(sourceLanguage.value)) sourceLanguage.value = 'auto';
  const pair = selectedLanguagePair.split('-');
  targetLanguage.value = sourceLanguage.value === 'auto' ? pair[1] : pair.find(language => language !== sourceLanguage.value);
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
        socket.send(JSON.stringify({ type: 'config', source_language: sourceLanguage.value, target_language: targetLanguage.value, language_pair: selectedLanguagePair, speaker_mode: speakerMode.value }));
      });
      configuration = null;
      if (socket !== sessionSocket || sessionSocket.readyState !== WebSocket.OPEN) return;
      const audio = { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true, voiceIsolation: true };
      if (inputDevice.value) audio.deviceId = { exact: inputDevice.value };
      let selectedStream;
      try {
        selectedStream = await navigator.mediaDevices.getUserMedia({ audio });
      } catch (error) {
        // Device IDs can change when macOS grants microphone permission. Retry
        // with the default input instead of ending the whole session.
        if (error.name !== 'OverconstrainedError' && error.name !== 'NotFoundError') throw error;
        selectedStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true, voiceIsolation: true } });
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
    if (event.type === 'segment_skipped') {
      incompleteSessions.add(event.session_id || captureSessionId);
      setDiagnostic(localized('超时段已跳过，继续接收最新发言', 'タイムアウトをスキップして最新の発言を受信', 'Timed-out segment skipped; receiving latest speech'));
      if (event.stage === 'translation') translationStatus.textContent = localized('本段超时已跳过', 'タイムアウト・スキップ', 'Timed out · skipped');
      else audioStatus.textContent = localized('识别超时已跳过', '認識タイムアウト・スキップ', 'Recognition timed out · skipped');
      return;
    }
    if (event.type === 'caption') {
      const captionKey = `${event.original_text || ''}\u0000${event.translated_text || ''}`;
      if (runtimeMode === 'MOCK' && mockCaptionKeys.has(captionKey)) return;
      if (runtimeMode === 'MOCK') mockCaptionKeys.add(captionKey);
      upsertCaption(event);
      lastCaptionAt = Date.now();
      setDiagnostic(event.skipped_stage ? localized('本段已跳过超时处理，原文保留', 'タイムアウト・原文を保持', 'Timed out; source retained') : event.is_final ? '已识别并翻译字幕' : '已识别原文，翻译处理中');
      renderCaptions(); updateSummary();
    }
    if (event.type === 'status') setDiagnostic(event.message);
    if (event.type === 'configured') {
      if (event.language_pair && event.source_language === 'auto') {
        recognitionLanguageStatus.textContent = `${event.language_pair.split('-').map(language => LANGUAGE_LABELS[language]).join(' / ')} · 自动识别`;
      } else updateRecognitionLanguage(event.asr_language || event.source_language);
      configuration?.resolve();
    }
    if (event.type === 'source_language_changed') {
      sourceLanguage.value = event.source_language || 'auto';
      sourceLanguageButtons.forEach(button => {
        const selected = button.dataset.language === sourceLanguage.value;
        button.classList.toggle('selected', selected);
        button.setAttribute?.('aria-pressed', String(selected));
      });
      if (event.target_language) targetLanguage.value = event.target_language;
      updateRecognitionLanguage(event.source_language);
      updateSummary();
      setDiagnostic(event.message || '源语言已更新');
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
      else if (event.state === 'silent' && event.message) setDiagnostic(event.message);
      else if (event.state === 'sound') setDiagnostic(localized('核心发言已捕获，正在识别', '主話者の音声を捕捉中・認識しています', 'Core speaker captured; recognizing'));
    }
    if (event.type === 'capture_paused') {
      stopCapture(); sessionEnding = true; setRuntime(false, '收音已暂停'); setDiagnostic(event.message); sendPendingAudio();
    }
    if (event.type === 'error') { setDiagnostic(`错误：${event.message}`); configuration?.reject(new Error(event.message)); }
    if (event.type === 'session_finished') {
      if (event.rejected_samples || event.dropped_samples || event.skipped_translations) incompleteSessions.add(captureSessionId);
      setDiagnostic(incompleteSessions.has(captureSessionId)
        ? localized('本次已结束，部分未接收或超时段已跳过，请核对记录', '終了しました。一部の未受信・タイムアウト区間をスキップしました', 'Finished; some missing or timed-out segments were skipped. Please review the record.')
        : '本次发言已完整收尾，可导出记录');
    }
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
  const body = transcriptParagraphs().map(row => `[${formatTime(row.start_ms)}] ${speakerLabel(row.speaker_id)}\n${row.original_text}\n${row.translated_text || ''}${row.chunks.some(chunk => chunk.skipped_stage) ? `\n[${localized('部分内容超时已跳过', '一部はタイムアウトでスキップ', 'Some content timed out and was skipped')}]` : ''}`).join('\n\n') || '暂无字幕';
  const text = incompleteSessions.size
    ? `[${localized('记录包含未接收或超时跳过的内容，可能不完整', '未受信・タイムアウトによる欠落があるため、記録は不完全な可能性があります', 'This record may be incomplete: some audio or translations were missing or timed out')}]\n\n${body}`
    : body;
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
clearBtn.addEventListener('click', () => { stopDemo(); captionRows = []; incompleteSessions.clear(); followCaptions = true; latestBtn.hidden = true; mockCaptionKeys.clear(); renderCaptions(); updateSummary(); });
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
asrEngine?.addEventListener('change', () => changeModelProvider('asr'));
translationEngine?.addEventListener('change', () => changeModelProvider('translation'));
asrServiceUrl?.addEventListener('change', () => refreshModelSelection('asr'));
translationServiceUrl?.addEventListener('change', () => refreshModelSelection('translation'));
asrModel?.addEventListener('change', () => { if (!SERVICE_DEFAULT_URLS[asrEngine.value]) checkAsrModel(); });
asrModel?.addEventListener('change', updateModelCompatibility);
translationModel?.addEventListener('change', updateModelCompatibility);
refreshModelsBtn?.addEventListener('click', refreshModelSelections);
downloadAsrBtn?.addEventListener('click', prepareSpeechModel);
chooseModelDirectoryBtn?.addEventListener('click', () => {
  if (window.webkit?.messageHandlers?.native) window.webkit.messageHandlers.native.postMessage({ type: 'choose_model_directory' });
  else modelDirectory?.focus();
});
sourceLanguage.addEventListener('change', () => { ensureDifferentLanguages('source'); updateSummary(); });
targetLanguage.addEventListener('change', () => { ensureDifferentLanguages('target'); updateSummary(); });
sourceLanguageButtons.forEach(button => button.addEventListener('click', () => setSourceLanguage(button.dataset.language)));
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
