# macOS 安装包

项目针对 Apple M3 / 16G 统一内存提供两种安装方式：源码运行适合开发和模型调试，DMG 适合日常启动。安装包只包含程序和界面，不包含 ASR、翻译或 TTS 模型权重。

## 从源码运行

```bash
cd local-meeting-interpreter
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[apple,translation]'
python -m meeting_interpreter.desktop
```

程序启动后会打开一个原生 macOS 窗口，页面嵌入在 App 内部，不会启动 Chrome、Edge 或其他浏览器。默认本地服务地址是 `http://127.0.0.1:8000`；如果 8000 已被旧实例或其他程序占用，程序会自动选择可用端口，并在页面底部显示本次实际地址。

如果之前打开过旧版本，先关闭旧的 `LocalMeetingInterpreter` 窗口，再启动新安装包，避免同时运行多个本地服务实例。

## DMG 本地模型配置

从 Finder 双击安装包时不会读取终端里的 `export` 环境变量。创建配置文件后，DMG 启动会自动使用 Ollama 和本地 ASR：

```bash
mkdir -p "$HOME/Library/Application Support/LocalMeetingInterpreter"
cat > "$HOME/Library/Application Support/LocalMeetingInterpreter/.env" <<'EOF'
MEETING_INTERPRETER_MODE=local
MEETING_INTERPRETER_TRANSLATION_BACKEND=ollama
MEETING_INTERPRETER_OLLAMA_MODEL=translategemma:4b
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

安装后第一次使用本地模型时仍需要准备模型缓存。不要把模型权重提交到 GitHub；可以在目标机器上下载，也可以把已验证的模型缓存复制到本机缓存目录。

## macOS 权限

首次打开 App 并点击开启音频输入时允许麦克风权限。使用腾讯会议或 Teams 的 BlackHole 回环设备时，先在会议软件中选择对应的扬声器输出，再在 App 中选择 BlackHole 输入。
