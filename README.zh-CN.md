# NMT · Neo Meeting Translater

**在 Mac 上运行的中文、日语、英语会议语音识别与实时双语字幕软件。**

[English](README.md) · [日本語](README.ja.md) · [下载最新版](https://github.com/elizzzzzz/Neo-Meeting-Translater/releases/latest) · [许可证](LICENSE)

## NMT 是做什么的

NMT 会听取一个音频来源，把讲话变成文字，并在屏幕上同时显示原文和译文。它适合现场会议、腾讯会议、Microsoft Teams 和网页视频。

选择本地语音识别和翻译模型后，音频、文字和模型都留在这台 Mac 上。当前版本以文字字幕为主，暂时不提供翻译语音播放。

当前版本：**v0.2.20** · Apple 芯片 Mac（arm64）· 原生 macOS App

## 目前可以做什么

- 中文 ↔ 日语、中文 ↔ 英语、英语 ↔ 日语。
- 在选定的语言对中自动判断当前发言语言。
- 自动判断不准确时，用按钮快速指定中文、日本語或 English。
- 连续保留同一段发言，识别结果可以修订，原文和译文并排显示，历史内容可以滚动查看。
- 可选匿名说话人标签。
- 半透明字幕浮窗：可以置顶、拖动、缩放，也可以只显示原文或只显示译文。
- 中文、日语、英语三种界面语言。
- 亮色、暗色或跟随系统外观。
- 翻译支持 Ollama、llama.app 或 SGLang 本地服务。
- 识别支持 Apple SpeechAnalyzer、MLX Whisper 或 SenseVoice。
- 显示本地模型状态、Ollama 状态、冷启动进度和输入音量。
- 保存设置后立即生效，不需要手动重启。

## 下载前需要准备什么

你需要：

- 一台 Apple 芯片 Mac。当前安装包是 arm64，Intel Mac 不能使用这个安装包。
- macOS 麦克风权限。
- 一个语音识别引擎和模型。Apple SpeechAnalyzer 需要 macOS 26 或更高版本；Whisper 和 SenseVoice 使用本地模型文件。
- 一个本地翻译服务。大多数用户选择 Ollama 即可。
- 如果要识别腾讯会议、Teams 或网页视频声音，需要 BlackHole 或 Loopback 这样的虚拟音频设备。

安装包不包含模型权重，这样下载文件更小，也方便你选择模型保存位置。

## 下载和打开

1. 打开[最新版发布页](https://github.com/elizzzzzz/Neo-Meeting-Translater/releases/latest)。
2. 下载 **NMT-portable.zip**。解压后双击 **NMT.app**，无需安装。
3. 或下载 **NMT.dmg**，打开后把 **NMT.app** 复制到你选择的文件夹。
4. 第一次采集声音时，允许 macOS 使用麦克风。
5. NMT 会打开为独立的 Mac 窗口，不会启动浏览器。

发布页还提供 **NMT-0.2.20.sha256**。如需检查下载文件，把校验文件和 ZIP、DMG 放在同一个文件夹中，打开“终端”执行：

~~~bash
shasum -a 256 -c NMT-0.2.20.sha256
~~~

安装包使用临时签名，尚未通过 Apple 公证。如果 macOS 第一次阻止打开，请在 Finder 中按住 Control 点击 NMT.app，选择“打开”并确认。

## 第一次设置

1. 打开“设置”。
2. 在“语音识别”中选择 Apple SpeechAnalyzer、Whisper 或 SenseVoice。
3. 在“翻译”中选择 Ollama、llama.app 或 SGLang。
4. 选择语言对：中日、中英或英日。
5. 选择 Mac 麦克风或音频回环输入。
6. 点击“保存并返回”。
7. 等待状态显示语音识别和翻译模型可用，再点击“开始”。

以后可以随时修改模型、服务、模型目录、语言对和外观。保存后立即生效，不需要重启。已有模型文件不会因为修改目录而自动移动。

## Ollama：最简单的本地翻译设置

Ollama 是大多数用户最容易使用的本地翻译服务。NMT 默认连接本机地址：**http://127.0.0.1:11434**。

### 安装并启动 Ollama

从 [ollama.com](https://ollama.com/download/mac) 下载 Ollama，打开 Mac App 并保持运行。NMT 的设置页面也提供“安装 Ollama”入口。

在“终端”检查：

~~~bash
ollama --version
ollama list
~~~

如果 ollama list 能正常显示，通常说明本地服务已经可以使用。回到 NMT 的“设置”，点击“重新检查”，确认显示“已安装”和“已连接”。

### 模型怎么选

对于 M3、16 GB 统一内存的 Mac：

| 需求 | 模型 | 简单建议 |
| --- | --- | --- |
| 实时字幕默认选择 | **translategemma:4b** | 先用这个，速度和质量比较均衡 |
| 更重视长句和措辞 | **translategemma:12b** | 质量更高，但速度更慢、占用更多内存 |
| 需要通用上下文纠错 | **qwen3:4b** | 通用能力较强，译文风格需要自行检查 |
| 内存紧张或试用 | **qwen2.5:3b** | 占用较小，质量低于上面几款 |

建议先安装一个模型：**translategemma:4b**。不要一开始安装多个模型。

~~~bash
ollama pull translategemma:4b
ollama list
~~~

然后在 NMT“设置”中选择“翻译服务：Ollama”，模型选择 **translategemma:4b**，点击“保存并返回”。第一次翻译可能较慢，因为模型需要冷启动；模型保持热启动后，后续句子会更快。

### 模型保存目录怎么设置

Ollama 通常使用自己的模型目录。在 NMT 设置里点击“使用 Ollama 当前目录”，软件会填入检测到的目录。ASR 模型或其他本地资源也可以使用你自己选择的目录。

修改 NMT 里的目录不会自动搬运 Ollama 已经管理的模型。如果想把 Ollama 的模型整体放到外置硬盘，请先在 Ollama 自己的设置中修改存储位置并重启 Ollama，再回到 NMT 点击“重新检查”。

### 已安装 Ollama，但 NMT 显示不可用

按下面顺序检查：

1. 打开 Ollama App，等待几秒。
2. 在终端执行 **ollama list**。
3. 确认 NMT 的服务是“Ollama”，地址是 **http://127.0.0.1:11434**。
4. 点击“重新检查”。
5. 确认模型名称和 ollama list 中完全一致。
6. 如果没有模型，执行 **ollama pull translategemma:4b**。
7. 如果刚改过模型目录，重启 Ollama，再重新检查。

NMT 只连接本机服务，不会把会议声音或字幕发送到远程翻译服务器。

## 会议和网页声音

### 使用 Mac 麦克风

在 NMT 选择内置麦克风或耳机麦克风，允许权限，然后点击“开始”。

### 使用腾讯会议、Teams 或网页视频

1. 安装 BlackHole 2ch 或 Loopback。
2. 在会议或视频软件里，把扬声器输出改为这个设备。
3. 在 NMT 中选择同一个设备作为输入。
4. 点击“开始”。

如果还想听到原声，可在 macOS“音频 MIDI 设置”中建立多输出设备，把耳机和虚拟音频设备一起加入。

NMT 一次读取一个输入设备。如果要同时采集自己的麦克风和远端声音，需要使用外部混音器或能提供混合输入的虚拟设备。

## 字幕模式

点击“字幕模式”打开小型半透明浮窗，把它拖到会议窗口的空白位置。可以选择原文和译文、仅原文或仅译文。

历史段落可以滚轮查看，最新段落保持在最下面。识别修订会更新当前段落，不会快速清空整段历史。

## 隐私和限制

- 选择本地引擎后，音频、识别文字、译文和模型都留在本机。
- NMT 不调用腾讯会议或 Teams 的云端转写。
- 房间嘈杂、声音太轻或多人同时说话时，识别可能出错。
- 说话人标签是匿名的，不会显示会议软件中的真实姓名。
- 延迟取决于模型、句子长度和 Mac 负载。“识别约一秒、翻译再增加一秒”是目标，不是保证。
- 当前版本以文字为主，翻译语音输出尚未提供。

## 商用授权和署名

NMT 的原创代码与文档采用 [Apache License 2.0](LICENSE)，允许商业使用、修改和分发，但必须遵守许可证条款。

再分发 NMT 时，请附带 LICENSE、NOTICE 及适用的第三方声明，并保留以下署名：

> 基于 NMT（Neo Meeting Translater），作者 elizzzzzz 及贡献者。项目来源：https://github.com/elizzzzzz/Neo-Meeting-Translater

模型、Apple 系统资源、Ollama、音频驱动和其他第三方组件仍遵循各自许可证。商业部署前请单独核对所选模型的授权条件。

遇到问题时，请提交 Issue，并写明软件版本、macOS 版本、所选模型和页面显示的具体状态。分享日志前请删除会议内容和个人信息。
\n