# macOS 安装包

项目针对 Apple M3 / 16G 统一内存提供三种运行方式：源码运行适合开发和模型调试，DMG 适合固定安装，免安装 ZIP 适合直接解压运行。安装包只包含程序和界面，不包含语音识别、翻译或 TTS 模型权重。

免安装方式：解压 `LocalMeetingInterpreter-portable.zip`，直接双击里面的 `LocalMeetingInterpreter.app`。App 不需要拖入 Applications，也不会启动浏览器。

## 从源码运行

```bash
cd local-meeting-interpreter
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[apple,translation]'
python -m meeting_interpreter.desktop
```

程序启动后会打开一个原生 macOS 窗口，页面嵌入在 App 内部，不会启动 Chrome、Edge 或其他浏览器。默认本地服务地址是 `http://127.0.0.1:8000`；如果 8000 已被旧实例或其他程序占用，程序会自动选择可用端口，并在页面底部显示本次实际地址。

点击“字幕浮窗”可切换为半透明、置顶、可移动的字幕窗口。浮窗会缩小到会议软件上方的一块区域，并可拖动标题栏移动；点击“退出浮窗”恢复完整工作台。App 使用单实例锁，重复双击安装包不会再启动第二个本地服务副本。

如果之前打开过旧版本，先关闭旧的 `LocalMeetingInterpreter` 窗口，再启动新安装包，避免同时运行多个本地服务实例。

## DMG 本地模型配置

从 Finder 双击安装包时不会读取终端里的 `export` 环境变量。创建配置文件后，DMG 启动会自动使用 Ollama 和本地 ASR：

```bash
mkdir -p "$HOME/Library/Application Support/LocalMeetingInterpreter"
cat > "$HOME/Library/Application Support/LocalMeetingInterpreter/.env" <<'EOF'
MEETING_INTERPRETER_MODE=local
MEETING_INTERPRETER_TRANSLATION_BACKEND=ollama
MEETING_INTERPRETER_OLLAMA_MODEL=translategemma:4b
MEETING_INTERPRETER_OLLAMA_KEEP_ALIVE=24h
MEETING_INTERPRETER_ASR_MODEL=mlx-community/whisper-medium-mlx-8bit
EOF
```

重新打开 DMG 后，页面右上角应显示 `LOCAL`，健康检查地址也会返回 `mode=local`。首次使用 Whisper 模型会下载模型权重；下载完成后，识别和翻译均在本机运行。

## 构建 DMG

```bash
cd local-meeting-interpreter
./scripts/build_macos_app.sh
```

在 Apple Silicon 上，脚本会使用当前 Python 架构构建。若系统默认 `python3` 不是 arm64，可指定 Homebrew 的 arm64 Python：

```bash
MEETING_INTERPRETER_BUILD_PYTHON=/opt/homebrew/bin/python3 ./scripts/build_macos_app.sh
```

构建产物：

- `dist/LocalMeetingInterpreter.app`
- `dist/LocalMeetingInterpreter.dmg`
- `dist/LocalMeetingInterpreter-portable.zip`

默认使用图标方案 A（双语气泡）。如需使用 B（声谱门）或 C（翻译书签）重新构建：

```bash
MEETING_INTERPRETER_ICON_VARIANT=b ./scripts/build_macos_app.sh
MEETING_INTERPRETER_ICON_VARIANT=c ./scripts/build_macos_app.sh
```

首次打开会出现三步使用提示。顶部“使用指南”可以再次查看；勾选“以后不再提醒”后，App 不会再次自动弹出。顶部“本地设置”会检查 Ollama 安装状态、运行状态、当前版本、最新版本和推荐模型，并提供升级、安装推荐模型和选择模型目录的入口。默认模型目录是 `~/Library/Application Support/LocalMeetingInterpreter/models`，更改后重新打开 App 生效。

安装后第一次使用本地模型时仍需要准备模型缓存。不要把模型权重提交到 GitHub；可以在目标机器上下载，也可以把已验证的模型缓存复制到本机缓存目录。

## macOS 权限

首次打开 App 并点击开启音频输入时允许麦克风权限。使用腾讯会议或 Teams 的 BlackHole 回环设备时，先在会议软件中选择对应的扬声器输出，再在 App 中选择 BlackHole 输入。
