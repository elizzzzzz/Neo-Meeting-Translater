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

程序启动后会自动打开 `http://127.0.0.1:8000`。

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

首次打开浏览器工作台时允许麦克风权限。使用腾讯会议或 Teams 的 BlackHole 回环设备时，先在会议软件中选择对应的扬声器输出，再在工作台中选择 BlackHole 输入。
