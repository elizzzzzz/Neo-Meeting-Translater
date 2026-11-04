# Local Meeting Interpreter

本地运行的中英 / 中日多人会议实时字幕翻译 MVP。当前目标设备是 16G 统一内存的 Apple M3：文字输出优先，语音合成作为可选插件，不依赖云端 API。

0.2.3 增加同一发言人的连续双栏记录、历史滚动与“回到最新”、手动换人及本地声纹自动分人（测试）。已完成的识别片段保留，当前片段可修订；停止录音会补齐尾句。记录保留在当前 App 会话内，退出前请导出。

“本地设置 → 语音转文字引擎”可选择 Whisper 或 SenseVoice（测试），保存并重开 App 生效。SenseVoice 需要本地 `asr/sensevoice/model.int8.onnx`、`tokens.txt`、`silero_vad.onnx`，不自动下载；原有 Whisper 配置保留。中日样本的实际结果、整句漏识别修复和限制见 [中日语音识别评估](docs/asr-evaluation-0.2.3.md) 与 [0.2.3 说明](docs/release-0.2.3.md)。自然多人会议准确率尚未验收，自动分人不能获得腾讯会议或 Teams 的真实姓名。

## 当前范围

- 麦克风或在线会议回环音频接入的后端接口
- 流式音频事件、说话人标签、原文和译文的数据模型
- 可替换的 ASR、说话人区分和翻译适配器
- 本地 FastAPI WebSocket 服务
- 原生 macOS 窗口中的实时字幕页面
- App 内音频设备选择，可选择 Mac 麦克风或 BlackHole 等会议回环设备
- 可切换半透明、置顶、可移动的字幕浮窗，覆盖在腾讯会议或 Teams 上方
- `mock` 模式用于在未下载模型时验证端到端流程

已接入 MLX Whisper、SenseVoice 和本地 Ollama/NLLB 适配器。语音输出尚未接入；当前以文字为主。未设置运行模式时仍默认 `mock`，设置 `MEETING_INTERPRETER_MODE=local` 后才加载本地模型。

如果已安装 Ollama，推荐使用 `translategemma:4b` 做本地翻译。先执行 `ollama pull translategemma:4b`，再使用以下配置：

```bash
export MEETING_INTERPRETER_MODE=local
export MEETING_INTERPRETER_TRANSLATION_BACKEND=ollama
export MEETING_INTERPRETER_OLLAMA_MODEL=translategemma:4b
python -m meeting_interpreter.desktop
```

Ollama 首次加载模型可能需要较长时间；后续翻译会复用已加载模型。若不设置 `MEETING_INTERPRETER_TRANSLATION_BACKEND=ollama`，项目继续使用 NLLB。

## 运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m meeting_interpreter --mock
```

在 M3 上安装真实 ASR 适配器：

```bash
pip install -e '.[apple,translation,speaker]'
export MEETING_INTERPRETER_MODE=local
export MEETING_INTERPRETER_ASR_MODEL=mlx-community/whisper-medium-mlx-8bit
export MEETING_INTERPRETER_TRANSLATION_MODEL=facebook/nllb-200-distilled-600M
python -m meeting_interpreter
```

安装包和界面说明见 [macOS 安装包](docs/macos-install.md)。发布目录同时提供 DMG 和免安装 ZIP：解压 `LocalMeetingInterpreter-portable.zip` 后直接双击 `LocalMeetingInterpreter.app` 即可运行，不需要写入 Applications，也不会启动 Chrome、Edge 或其他浏览器。

首次打开 App 会显示使用提示，并自动检查 Ollama 是否安装、服务是否运行、版本是否有更新以及推荐翻译模型 `translategemma:4b` 是否已下载。点击“本地设置”可以重新检查、尝试通过 Homebrew 升级 Ollama、安装推荐模型，并选择语音识别模型缓存目录（翻译模型仍由 Ollama 管理）。使用提示偏好独立保存在本机，不受服务端口变化影响；勾选“以后不再提醒”可以关闭启动提示；之后仍可从顶部“使用指南”再次打开。

界面中的 ASR 已标注为“语音识别”，Ollama 已标注为“本地翻译引擎”，模型状态和冷启动进度使用中文显示，方便非技术人员判断当前是否可以开始会议。

启用本地多人区分：

```bash
pip install -e '.[diarization]'
export HF_TOKEN=你的_HuggingFace_访问令牌
export MEETING_INTERPRETER_SPEAKER_MODE=pyannote
export MEETING_INTERPRETER_MAX_SPEAKERS=4
python -m meeting_interpreter
```

首次下载 pyannote 模型时需要在 Hugging Face 接受模型使用条件；下载完成后可以切换为本地模型目录，推理过程不需要联网。M3/16G 建议先使用 CPU 说话人区分，避免和 MLX Whisper、NLLB 同时占用统一内存。

首次使用会按 `MEETING_INTERPRETER_ASR_MODEL` 下载 MLX Whisper 权重；App 启动后会自动冷启动 ASR 和翻译模型，界面显示加载进度，准备完成后保持热启动。M3/16G 默认使用 8-bit medium 模型，在保留本地翻译和 App 运行空间的同时提高中文、日文和英文会议识别准确率。若设备内存紧张，可手动切换为 `mlx-community/whisper-small-mlx-8bit`。

打开 App，选择输入设备后点击“开启音频输入”。界面支持中文 ↔ 日本語、中文 ↔ English 两组双向方向，可用快捷按钮或交换按钮切换；源语言也可以保留为“自动识别”。

## 未连接模型时体验界面

点击“演示字幕”即可预览中文、日文、英文示例文字、临时字幕更新为完整字幕、两位示例发言人、字幕滚动和半透明浮窗。示例不读取麦克风、不调用真实模型，不能代表识别精度或多人区分效果。停止和清空按钮可以随时结束演示；原生 App 的“导出记录”使用 macOS 保存对话框，将原文和译文保存为 UTF-8 文字文件。

没有模型或模型未就绪时，真实音频输入按钮保持禁用；顶部和右侧会显示具体状态。真实识别、翻译延时及腾讯会议 / Teams 音频接入需在模型连接后另行验证。

开发验证：`pytest -q`、`node --test tests/frontend.test.cjs`；安装 Playwright 和 Chromium 后可以运行 `python scripts/smoke_workspace.py`，检查桌面单屏布局、设置输入保持、示例字幕与浮窗。此检查不连接真实模型。

## 服务接口

- `GET /health`：健康检查
- `WS /ws`：接收 JSON 音频事件并返回实时字幕事件

腾讯会议和 Teams 的 macOS 音频回环配置见 [macOS 会议音频接入](docs/macos-meeting-audio.md)。

WebSocket 输入示例：

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

## 设计约束

1. 临时字幕可以被后续 ASR / 翻译结果修正。
2. 稳定字幕才进入可选 TTS 队列，避免重复播放。
3. 说话人默认显示为 `SPEAKER_00` 等匿名标签；声纹登记在后续版本加入。
4. 所有模型文件放在本机缓存目录，运行时不调用云端服务。

## 后续里程碑

- `M1`：在 M3 上接入 MLX Whisper 或 whisper.cpp 的真实流式 ASR。
- `M2`：已接入可选 pyannote Community-1 说话人区分，默认限制 2–4 位并发说话人。
- `M3`：接入 NLLB-200 600M 的中英 / 中日翻译。
- `M4`：接入 BlackHole、WASAPI Loopback 或 PipeWire 音频适配器。
- `M5`：按需加载 VoxCPM2，输出翻译语音。

## GitHub

本项目预期上传到 GitHub 私有仓库。模型权重不提交到 Git；请使用本地缓存或私有制品存储。
