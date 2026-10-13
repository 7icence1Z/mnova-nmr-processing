# Windows / macOS 共用执行入口

`scripts/mnova_runner.py` 是 Python 3.9+ 标准库启动器，不需要 NumPy、Pillow 或第三方 Python 包。它执行已有零参数 `.qs` 函数，不做全谱自动分析，也不替代生成与独立核验脚本。化学判断、原生对象和排版逻辑继续按本 skill 执行。

## 安装发现与能力检查

先在 skill 目录运行以下命令；macOS 使用 `python3`，Windows 可以用 `python` 或当前环境的 Python 绝对路径。

```sh
python3 scripts/mnova_runner.py doctor
python3 scripts/mnova_runner.py --mnova "/Applications/MestReNova.app" doctor
```

优先级为 `--mnova`、环境变量 `MNOVA_EXECUTABLE`、自动发现。macOS 扫描 `/Applications` 和 `~/Applications` 下 Mnova/MestReNova 名称的 `.app`，读取 `Contents/Info.plist` 的 `CFBundleExecutable`，直接启动 `Contents/MacOS/` 内的程序，不使用 `open -a`，也不假定程序名称。Windows 查注册表安装目录、常见目录和 PATH。多个安装并存时要求显式选择，避免静默切换版本。

`doctor` 调用当前程序的 `--help`，检查 `--nogui`、`--wait`、`--sf` 和 `--logfile`，输出程序路径和可能的资源目录。资源文档可能位于 macOS bundle 的 `Contents/Resources` 或 `Contents/SharedSupport`，按实际文件查找。命令行参数存在不代表许可证、字体或全部 API 已通过验证。

## 运行处理和核验脚本

处理脚本使用绝对输入/输出路径，零参数入口不加括号。启动器复制脚本到本次日志目录并追加完成标记，因此不要让脚本依赖自身文件位置；外部资源路径必须显式传入或写成已确认的绝对路径。

```sh
python3 scripts/mnova_runner.py run --script "/path/to/process.qs" --function processSpectrum --run-dir "/path/to/run-logs" --expect "/path/to/result.mnova"
python3 scripts/mnova_runner.py run --script "/path/to/verify.qs" --function verifySpectrum --run-dir "/path/to/run-logs" --expect "/path/to/page.png"
```

`--expect` 可重复，检查文件存在、非空且本次更新；仍需核验原生对象和实际页面。`--timeout` 默认 180 秒；工作目录默认程序所在目录，有当前版本证据时可用 `--cwd` 改变。所有进程参数以数组传递，路径中的空格和中文不经过 shell 拼接。生成的 `.qs` 为 UTF-8 BOM，嵌入标记路径时使用 JSON 字符串转义。

每次运行在 `--run-dir` 下创建独立子目录，保存 `wrapped.qs`、`mnova.log`、标准输出、标准错误、完成标记和 `result.json`。只有函数正常返回并写出标记、进程正常结束且预期输出通过检查，启动器才返回成功；退出码 0 无标记仍算失败。不自动重试或结束用户现有 Mnova 会话。超时只终止本次启动的进程；如已转交旧实例，该实例仍可能继续运行，先检查日志再决定下一步。

## macOS 需要实际验证的部分

- 使用用户已安装、已激活的版本；不要求更换产品或安装 Mnova Console。若本版不提供所需无界面接口，报告具体缺项。
- 由系统执行已有 bundle 中的程序，不自动改签名、隔离属性或强制指定 Intel/ARM 架构。架构或系统执行失败时保留错误信息。
- 用同一原生 API 的小型脚本核验 File/TextStream、脚本编码、谱图保存、重新读取和 `toPixmap`，再运行样品。Windows 实测成功不能替代真实 Mac 测试。
- Times New Roman 必须按实际字体确认。中文字体从当前 Mac 安装字体选择适合的衬线字体，不能硬编码 Windows 的 SimSun；Times New Roman 缺失时报告，不静默替换。
- 页面字号、字距和对象边界以重新打开后的 Mnova 渲染为准，不能只用 Python 图像推断跨平台版式一致。

官方资料：[Mnova 脚本入门](https://mestrelab.com/starting-guides/how-to-get-started-with-mnova-scripts.html)；[命令行脚本说明](https://www.mestrelabcn.com/Manual_HTML_Mnova_15/new_item.htm)。文档和参数按用户实际版本核对。

## 已检查的 Mnova 17 Mac 安装包

对用户提供的 `MestReNova-17.0.1-41952.dmg` 做过静态解包检查，没有在 Windows 运行 Mac 程序，也没有将厂商二进制或原始脚本纳入仓库。

- DMG 是 APFS 卷，内含 `MestReNova.app`；版本字段为 `17.0.1.41952`，bundle ID 为 `com.mestrelab.MestReNova`。
- `CFBundleExecutable` 是 `MestReNova`，程序路径为 `Contents/MacOS/MestReNova`。Mach-O fat header 包含 `x86_64` 和 `arm64` 两个切片。
- 此 DMG 的 Info.plist XML 属性引号包含字面 `\"`，标准 plistlib 会报 XML 解析错误。启动器仅对此已识别的 XML 头形式在内存中去除引号转义后解析，不改写安装包；其他损坏 plist 不猜测程序名。
- 官方 `.qs` 在 `Contents/Resources/scripts/`，示例在其 `examples/` 子目录。保留 File/TextStream、`Integral`、`Multiplet`、预处理和 `serialization.save` 示例；不是 Windows 的 `examples/scripts/` 路径。
- 卷目录包含 `Contents/PlugIns/libScriptingPlugin.dylib`、`libPyScriptingPlugin.dylib`、QtScript 框架和 `Contents/python/` 的 Python 3.11。存在 Python 插件不代表 QtScript 应迁移到未经验证的 Python NMR API，现有 `.qs` 流程继续使用。
- 在主程序二进制中找到 `nogui`、`logfile`、`scriptFunction` 等参数相关字符串，这是静态线索，不等于实际 `--help` 和脚本执行通过。安装包未找到独立的 `documents/scripts/*.html`；本版按随附 `.qs` 示例与当前在线/应用帮助核对 API，不要求该路径一定存在。

启动器已用实际解出的 bundle 核验程序解析；跨平台路径及异常处理有单元测试。Mac 的实际命令行启动、许可证、字体和完整 NMR 页面渲染仍需真实 macOS 验证。
