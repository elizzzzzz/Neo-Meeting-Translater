# 模型与本地服务配置

[返回中文版 README](../README.zh-CN.md) · [English README](../README.md)

## 首次配置

1. 打开 App，阅读“把会议内容留在本机”的使用提示。
2. 在“模型与服务设置”中检查本机环境。
3. 选择语音识别引擎和翻译服务。
4. 选择模型保存目录。默认使用当前 Ollama 模型目录，也可以随时改为其他本地目录。
5. 点击“保存并返回”，自动回到主界面，设置立即应用；如果正在录音，App 会先收尾并暂时暂停收音，模型就绪后自动恢复。切换期间可能产生音频缺口。
6. 看到“模型可用 · 热启动”后，再开始会议。

App 会显示 Ollama 是否已安装、服务是否运行、当前版本、可检查到的最新版本，以及推荐翻译模型状态。安装或升级 Ollama、安装模型和下载 ASR 权重都需要用户在界面中明确点击；程序不会在后台自行下载或升级。

配置保存后，下次打开不会再次弹出设置引导，旧版已有配置也会自动识别。未完成配置时，也可以勾选“以后不再提醒”。需要时随时从侧栏“使用指南”或“本地设置”打开。

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


## 模型授权

模型权重、推理框架和音频驱动分别遵循其原有许可证。NMT 的 Apache-2.0 许可证不授予第三方模型或组件的权利；商用部署前请核对所选模型和依赖的许可条件。参见 [第三方说明](../THIRD_PARTY_NOTICES.md)。
