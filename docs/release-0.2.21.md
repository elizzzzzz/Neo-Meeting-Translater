# NMT 0.2.21

本版本修复 macOS 安装包的交付方式：

- 新增标准 `NMT.pkg` 双击安装器，默认将 NMT 安装到“应用程序”。
- DMG 增加标准“应用程序”快捷方式，打开 DMG 后拖放安装，不会把磁盘映像误当作安装器直接运行。
- 保留 `NMT-portable.zip` 免安装包，便于测试和临时使用。
- 构建脚本支持 Developer ID 应用签名、安装器签名和 Apple 公证；没有证书时仍生成可运行的 ad-hoc 测试包，并明确标识未公证状态。
- 发布验证增加 PKG 载荷检查、DMG `/Applications` 快捷方式检查，以及 ZIP/DMG/App 的 arm64 和签名检查。

本机没有可用的 Developer ID 证书或公证凭据，因此本次本地构建只能验证包结构和运行完整性，不能宣称已消除 Gatekeeper 的“程序严重不安全”提示。正式公开发布时，请按 `docs/macos-install.md` 配置证书和公证凭据后重新构建。

交付文件：

- `NMT-portable.zip`：免安装包。
- `NMT.dmg`：拖放到“应用程序”的磁盘映像。
- `NMT.pkg`：双击安装器。
