# NMT · Neo Meeting Translater

> 当前源码：NMT 0.2.18，采用 LM Studio 风格的深色工作区。新构建产物命名为 `NMT.app`、`NMT-portable.zip` 和 `NMT.dmg`。本机已构建并验证 0.2.18；GitHub 已发布的 0.2.17 安装包仍为旧界面。名称变更保留原配置、模型目录和麦克风授权。

在 Apple Silicon Mac 上本地运行的多人会议字幕翻译工具，面向中文、日语和英语会议。应用优先提供实时文字字幕，音频和模型留在本机，不调用云端转写或翻译 API。

当前源码版本：**0.2.18** · 已发布安装包：**0.2.17**
适用设备：Apple M3 / 16 GB 统一内存（也可在其他 macOS Apple Silicon 设备上运行）
交付形式：macOS 原生 App、免安装 ZIP、DMG

![NMT 双语工作区（明确标注的界面测试字幕，非实时识别）](docs/images/nmt-workspace.png)

## 主要功能

- 中文、日语、英语之间的双向翻译：
  - 中文 ↔ 日本語
  - 中文 ↔ English
  - English ↔ 日本語
- 实时原文和译文双栏字幕，默认保持固定语言顺序。
- 自动识别源语言，或用按钮快速锁定当前发言语言。
- 多人发言记录、连续段落、历史滚动和回到最新位置。
- 说话人标签与可选的本地说话人区分；默认显示匿名标签。
- 半透明、置顶、可移动、可缩放的字幕浮窗。
- 支持本机麦克风，以及通过 BlackHole / Loopback 接入腾讯会议、Microsoft Teams 和网页视频的系统音频。
- 支持 Apple SpeechAnalyzer、MLX Whisper、SenseVoice，以及 Ollama / llama.app / SGLang 兼容的本地服务。
- 修改模型、服务地址和模型目录后立即应用，不需要重启 App。
- 启动时显示使用提示和模型准备进度；准备完成后自动收起非主要信息，把空间留给字幕。
- 单实例运行，重复打开不会启动多个本地服务副本。

当前版本以文字输出为主，翻译语音输出尚未完成。

## 下载和运行

从 [v0.2.17 发布页](https://github.com/elizzzzzz/local-meeting-interpreter/releases/tag/v0.2.17) 下载（私有仓库需要登录有访问权限的 GitHub 账号）：

- `LocalMeetingInterpreter-portable.zip`：解压后直接双击 `LocalMeetingInterpreter.app`，不需要拖入 Applications。
- `LocalMeetingInterpreter.dmg`：适合按 macOS 常规方式安装。

安装包不包含 ASR、翻译或 TTS 模型权重，也不会把模型提交到 GitHub。首次使用时，在 App 的“模型与服务设置”中选择本地引擎、模型目录和服务地址。

字幕页面嵌在原生 macOS App 窗口中，无需打开独立浏览器。当前安装包面向 Apple Silicon（arm64），使用本地临时签名，未进行 Apple 公证。

更多安装和权限说明见 [macOS 安装包](docs/macos-install.md)。

## 首次配置

1. 打开 App，阅读“把会议内容留在本机”的使用提示。
2. 在“模型与服务设置”中检查本机环境。
3. 选择语音识别引擎和翻译服务。
4. 选择模型保存目录。默认使用当前 Ollama 模型目录，也可以随时改为其他本地目录。
5. 点击保存。设置会立即应用；如果正在录音，App 会先收尾并暂时暂停收音，模型就绪后自动恢复。切换期间可能产生音频缺口。
6. 看到“模型可用 · 热启动”后，再开始会议。

App 会显示 Ollama 是否已安装、服务是否运行、当前版本、可检查到的最新版本，以及推荐翻译模型状态。安装或升级 Ollama、安装模型和下载 ASR 权重都需要用户在界面中明确点击；程序不会在后台自行下载或升级。

使用提示可以勾选“以后不再提醒”。之后仍可从顶部“使用指南”重新打开。

## 语音识别引擎

### Apple SpeechAnalyzer

Apple SpeechAnalyzer 是 macOS 26+ 的本机语音识别引擎。它只负责语音转文字，翻译仍由独立的本地翻译模型完成。

- Apple 语言资源由 macOS 管理，不保存在自定义模型目录中。
- 只有点击“准备 Apple 语言资源”后，系统才会按需准备资源。
- 中文、日语和英语资源的可用性取决于当前 macOS 安装情况。
- 当前版本已完成接入和只读资源检测，但真实中文、日语识别准确率与端到端延时尚未完成正式实测。

Apple 引擎的双语自动识别目前属于应用层候选比较实验功能。需要稳定识别时，可使用字幕区域上方的源语言按钮锁定中文、日本語或 English。

### MLX Whisper

适合 Apple Silicon 的本地识别方案，可通过界面选择模型和缓存目录。源码运行时也可以使用环境变量：

```bash
export MEETING_INTERPRETER_MODE=local
export MEETING_INTERPRETER_ASR_MODEL=mlx-community/whisper-medium-mlx-8bit
```

M3 / 16 GB 建议从 8-bit medium 开始；如果内存紧张，可改用 `mlx-community/whisper-small-mlx-8bit`。

### SenseVoice

SenseVoice 作为可选本地引擎接入。使用前需要把模型文件放在所选目录中：

```
asr/sensevoice/model.int8.onnx
asr/sensevoice/tokens.txt
asr/sensevoice/silero_vad.onnx
```

程序不会自动下载这些文件。

## 翻译模型和本地服务

发布的 App 通过 Ollama、llama.app 或 SGLang 连接本地翻译模型。Ollama / llama.app / SGLang 负责管理各自的模型文件，App 通过配置的本机服务地址调用它们。NLLB 适配器需要额外安装 Python 依赖，仅用于源码运行，不包含在当前精简安装包中。

Ollama 示例：

```bash
ollama pull translategemma:4b
```

源码运行示例：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[apple,audio,speaker]'

export MEETING_INTERPRETER_MODE=local
export MEETING_INTERPRETER_TRANSLATION_BACKEND=ollama
export MEETING_INTERPRETER_OLLAMA_MODEL=translategemma:4b

python -m meeting_interpreter.desktop
```

推荐模型是 `translategemma:4b`，但可以在 App 中更换为本机服务支持的其他模型。模型目录变更后会重新检测并立即应用；现有模型文件不会自动迁移。

### SGLang

设置中的“文字翻译 → SGLang”连接本机 OpenAI 兼容接口，默认地址为 `http://127.0.0.1:30000`。先在终端或自己的启动脚本中启动 SGLang，再回到 App 刷新模型列表；App 不会替 SGLang 下载权重，也不会修改它的模型目录。

SGLang 启动示例（模型路径可替换为本地目录）：

```bash
python -m sglang.launch_server \
  --model-path tencent/HY-MT1.5-1.8B \
  --served-model-name hy-mt1.5-1.8b \
  --host 127.0.0.1 \
  --port 30000
```

推荐先测试 `tencent/HY-MT1.5-1.8B`：它是专用多语翻译模型，适合中、日、英互译和低延迟字幕；如果需要更强的上下文和术语能力，可再比较 `tencent/HY-MT1.5-7B`，但 M3 / 16 GB 更容易受到内存和首 token 延迟影响。通用备选是 Qwen3 4B 级指令模型，适合需要上下文纠错、术语约束和翻译之外文本处理的场景。

SGLang 是推理服务框架，所谓“SGLang 格式”实际是它支持的 Hugging Face 模型权重和 OpenAI 兼容服务接口。具体模型是否能在当前 SGLang 构建和 Apple Metal 环境启动，需要在目标机器上单独验证；本项目目前只验证了服务发现、配置保存、流式接口和断线提示，没有把模型权重下载到仓库或自动安装。

## 会议和网页音频接入

App 一次采集一个输入设备：

- 现场会议：选择 Mac 内置麦克风或耳机麦克风。
- 腾讯会议、Microsoft Teams、网页视频：安装 BlackHole 2ch 或 Loopback，把会议软件的扬声器输出设置为回环设备，再在 App 中选择同名输入设备。
- 需要同时听到原声时，可在 macOS“音频 MIDI 设置”中建立多输出设备。

详细步骤见 [macOS 会议音频接入](docs/macos-meeting-audio.md)。

应用不会调用腾讯会议或 Teams 的云端转写接口。回环设备只是把系统音频作为本地输入交给识别管线。

## 本地服务接口

源码运行时提供以下本地接口，便于集成自己的音频采集器：

- `GET /health`：查看服务状态和当前运行模式。
- `WS /ws`：发送音频事件并接收实时字幕事件。

音频事件示例：

```json
{
  "type": "audio",
  "session_id": "demo",
  "audio_base64": "...",
  "sample_rate": 16000,
  "channels": 1,
  "source": "microphone"
}
```

## 字幕模式

点击“字幕模式”进入只显示真实收到的原文和译文的半透明浮窗。它不会生成模拟字幕。

浮窗支持：

- 置顶、拖动和缩放；
- 双栏显示、仅源文、仅译文；
- 历史记录滚轮查看（记录保留在本次会话中，退出前请导出）；
- 固定语言双栏：中日为中文在左、日文在右；中英为中文在左、英文在右；英日为英文在左、日文在右；“源 / 译”标志随发言语言切换；
- 记录导出为 UTF-8 文本。

“源 / 译”标志只在检测到新段落或源语言发生变化时显示，避免连续发言时反复闪烁。源语言选择按钮可以在识别不确定时立即锁定语言。

## 本地隐私

- 音频、识别结果、翻译结果和模型文件默认留在本机。
- 不提交或内置模型权重。
- Ollama / llama.app / SGLang 仅访问配置的本机服务地址。
- App 不会因为启动、刷新模型列表或打开设置而自动下载 Apple 语言资源、ASR 模型或 Ollama 模型。
- 导出的会议记录由用户主动选择保存位置。

## 已知限制

- Apple SpeechAnalyzer 需要 macOS 26+。
- Apple 语言资源受 macOS 版本和系统安装状态影响；它们不受 App 自定义模型目录控制。
- 尚未完成真实 Apple 中文、日语识别准确率和会议端到端延时的正式基准测试。
- Apple 引擎的双语自动判断是应用层候选比较实验功能；嘈杂或短句场景建议使用源语言按钮。
- 录音中保存设置会短暂停止收音，切换期间可能缺少少量音频。
- 说话人区分只能生成匿名标签，不能从会议软件获得真实姓名；混合回环音频中的多人同时讲话会降低区分效果。
- 语音合成输出尚未完成，当前交付以文字字幕为主。
- 会议音频需要 macOS 音频回环设备，App 本身不会直接读取腾讯会议或 Teams 的内部音频通道；真实麦克风、腾讯会议和 Teams 回环采集仍需在目标设备单独验收。
- 无法保证所有会议场景达到识别约 1 秒、翻译再增加约 1 秒的目标；实际延时受模型、音频长度、噪声和设备负载影响。

## 开发者运行

```bash
git clone https://github.com/elizzzzzz/local-meeting-interpreter.git
cd local-meeting-interpreter

python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m meeting_interpreter --mock
```

启动桌面 App（需先安装桌面和音频依赖）：

```bash
pip install -e '.[apple,audio,speaker]'
python -m meeting_interpreter.desktop
```

运行测试：

```bash
pytest -q
node --test tests/frontend.test.cjs
```

构建 arm64 安装包：

```bash
pip install -e '.[apple,audio,installer,speaker]'
./scripts/build_macos_app.sh
```

构建结果：

- `dist/NMT.app`
- `dist/NMT-portable.zip`
- `dist/NMT.dmg`

默认使用 NMT 图标，也可通过 `MEETING_INTERPRETER_ICON_VARIANT=a|b|c` 选择三种内置图标方案后重新构建。

## 文档与评估

- [0.2.18 NMT 视觉更新](docs/release-0.2.18.md)

- [0.2.17 设置即时生效说明](docs/release-0.2.17.md)
- [0.2.16 Apple SpeechAnalyzer 接入说明](docs/release-0.2.16.md)
- [中日识别评估](docs/asr-evaluation-0.2.3.md)
- [长段中日语音回放评估](docs/asr-evaluation-0.2.4.md)

## 版本 0.2.17

本版本重点是“设置保存后立即生效”：

- 模型、服务地址和模型目录无需重启即可应用。
- 录音中切换设置会安全收尾旧音频，模型就绪后自动恢复。
- 连续保存时只采用最新配置，旧检测结果不会覆盖新状态。
- 加载失败会显示具体原因，可修改设置后直接重试。
- Apple SpeechAnalyzer 资源仍需用户显式点击准备。
- 原生 macOS 窗口、字幕浮窗、中文状态说明和单实例行为保持可用。

已有的 0.2.17 构建验证记录如下；本次发布仅整理文档并上传同一组安装包：

- 148 项 Python 测试通过，1 项跳过。
- 58 项前端测试通过。
- Chromium 界面回归通过。
- arm64 ZIP 解压、DMG 挂载、可执行权限和签名检查通过。
- 验证使用隔离配置与模拟识别/翻译，不下载模型、不录制真实麦克风、不改变用户模型设置。

完整变更记录见 [docs/release-0.2.17.md](docs/release-0.2.17.md)。
