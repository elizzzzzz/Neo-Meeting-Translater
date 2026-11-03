# Local Meeting Interpreter

本地运行的中英 / 中日多人会议实时字幕翻译 MVP。当前目标设备是 16G 统一内存的 Apple M3：文字输出优先，语音合成作为可选插件，不依赖云端 API。

## 当前范围

- 麦克风或在线会议回环音频接入的后端接口
- 流式音频事件、说话人标签、原文和译文的数据模型
- 可替换的 ASR、说话人区分和翻译适配器
- 本地 FastAPI WebSocket 服务
- 原生 macOS 窗口中的实时字幕页面
- App 内音频设备选择，可选择 Mac 麦克风或 BlackHole 等会议回环设备
- 可切换半透明、置顶、可移动的字幕浮窗，覆盖在腾讯会议或 Teams 上方
- `mock` 模式用于在未下载模型时验证端到端流程

真实模型适配器预留给后续迭代：Apple Silicon 优先使用 MLX/whisper.cpp，翻译使用本地 NLLB，VoxCPM2 只在需要语音输出时按需加载。

当前已经接入 MLX Whisper 和 NLLB 适配器；默认仍是 `mock`，设置 `MEETING_INTERPRETER_MODE=local` 后才加载本地模型。

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
pip install -e '.[apple,translation]'
export MEETING_INTERPRETER_MODE=local
export MEETING_INTERPRETER_ASR_MODEL=mlx-community/whisper-medium-mlx-8bit
export MEETING_INTERPRETER_TRANSLATION_MODEL=facebook/nllb-200-distilled-600M
python -m meeting_interpreter
```

安装包和界面说明见 [macOS 安装包](docs/macos-install.md)。安装包是独立的 macOS App，内部使用原生窗口嵌入本地工作台，不会启动 Chrome、Edge 或其他浏览器。

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
