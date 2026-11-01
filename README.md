# Local Meeting Interpreter

本地运行的中英 / 中日多人会议实时字幕翻译 MVP。当前目标设备是 16G 统一内存的 Apple M3：文字输出优先，语音合成作为可选插件，不依赖云端 API。

## 当前范围

- 麦克风或在线会议回环音频接入的后端接口
- 流式音频事件、说话人标签、原文和译文的数据模型
- 可替换的 ASR、说话人区分和翻译适配器
- 本地 FastAPI WebSocket 服务
- 浏览器实时字幕页面
- 浏览器音频设备选择，可选择 Mac 麦克风或 BlackHole 等会议回环设备
- `mock` 模式用于在未下载模型时验证端到端流程

真实模型适配器预留给后续迭代：Apple Silicon 优先使用 MLX/whisper.cpp，翻译使用本地 NLLB，VoxCPM2 只在需要语音输出时按需加载。

## 运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m meeting_interpreter --mock
```

打开 <http://127.0.0.1:8000>，选择输入设备后点击“开启本地麦克风”。默认后端会产生模拟的中日 / 中英会议字幕事件；接入真实模型后，浏览器协议保持不变。

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
- `M2`：加入轻量在线说话人区分，限制 2–4 位并发说话人。
- `M3`：接入 NLLB-200 600M 的中英 / 中日翻译。
- `M4`：接入 BlackHole、WASAPI Loopback 或 PipeWire 音频适配器。
- `M5`：按需加载 VoxCPM2，输出翻译语音。

## GitHub

本项目预期上传到 GitHub 私有仓库。模型权重不提交到 Git；请使用本地缓存或私有制品存储。
