# Windows / macOS 共用执行入口

`scripts/mnova_runner.py` 是 Python 3.9+ 标准库启动器，不需要 NumPy、Pillow 或第三方 Python 包。它执行已有零参数 `.qs` 函数，不做全谱自动分析，也不替代生成与独立核验脚本。化学判断、原生对象和排版逻辑继续按本 skill 执行。

## 安装发现与能力检查

先在 skill 目录运行以下命令；macOS 使用 `python3`，Windows 可以用 `python` 或当前环境的 Python 绝对路径。

```sh
python3 scripts/mnova_runner.py doctor --static
python3 scripts/mnova_runner.py doctor
python3 scripts/mnova_runner.py --mnova "/Applications/MestReNova.app" doctor
```

优先级为 `--mnova`、环境变量 `MNOVA_EXECUTABLE`、自动发现。macOS 扫描 `/Applications` 和 `~/Applications` 下及一层厂商子目录中 Mnova/MestReNova 名称的 `.app`，按大小写无关的名字匹配，以适应大小写敏感卷；读取 `Contents/Info.plist` 的 `CFBundleExecutable`，直接启动 `Contents/MacOS/` 内的程序，不使用 `open -a`，也不假定程序名称。Windows 查注册表安装目录、常见目录和 PATH。多个安装并存时要求显式选择，避免静默切换版本。

`doctor --static` 只读取 bundle 元数据、资源路径及 Mach-O 文件头，不启动 Mnova、不运行 `--help`，状态为 `static_only_not_executed`。已发生启动崩溃的 Mac 优先用此模式收集安装信息，再选择 GUI 路径。它能区分 Intel、ARM 或双架构文件，但不能推断当前硬件、实际执行切片或许可证状态；`launcher_machine` 也可能属于 Rosetta 下的启动器。Apple 说明 [Universal 程序既可原生运行也可转译运行](https://developer.apple.com/documentation/apple-silicon/about-the-rosetta-translation-environment)，因此不能将文件中有 ARM 切片等同于实际运行的是 ARM。

不带 `--static` 的 `doctor` 调用当前程序的 `--help`，检查 `--nogui`、`--wait`、`--sf` 和 `--logfile`，输出程序路径和可能的资源目录。probe 保存 stdout/stderr、退出码、bundle 版本和标识、启动器所见架构及结果 JSON；即使预检超时，也保留超时异常中已经捕获的输出，避免丢失启动错误。可用 `doctor --run-dir "/path/to/diagnostics"` 指定目录，默认系统临时目录。资源文档可能位于 macOS bundle 的 `Contents/Resources` 或 `Contents/SharedSupport`，按实际文件查找。命令行参数存在不代表许可证、字体或全部 API 已通过验证。

## 运行处理和核验脚本

处理脚本使用绝对输入/输出路径，零参数入口不加括号。启动器复制脚本到本次日志目录并追加完成标记，因此不要让脚本依赖自身文件位置；外部资源路径必须显式传入或写成已确认的绝对路径。

```sh
python3 scripts/mnova_runner.py run --script "/path/to/process.qs" --function processSpectrum --run-dir "/path/to/run-logs" --expect "/path/to/result.mnova"
python3 scripts/mnova_runner.py run --script "/path/to/verify.qs" --function verifySpectrum --run-dir "/path/to/run-logs" --expect "/path/to/page.png"
```

`--expect` 可重复，检查文件存在、非空且本次更新；仍需核验原生对象和实际页面。`--timeout` 默认 180 秒；工作目录默认程序所在目录，有当前版本证据时可用 `--cwd` 改变。所有进程参数以数组传递，路径中的空格和中文不经过 shell 拼接。生成的 `.qs` 为 UTF-8 BOM，嵌入标记路径时使用 JSON 字符串转义。

输入脚本、函数名、输出是否覆盖脚本、有效工作目录及有限正数超时在任何 Mnova 启动前检查。脚本、工作目录、运行日志目录支持引号中的 `~/...`；错误输入不应触发一次有风险的预检启动。

每次运行在 `--run-dir` 下创建独立子目录，保存 `wrapped.qs`、`mnova.log`、标准输出、标准错误、完成标记和 `result.json`。只有函数正常返回并写出标记、进程正常结束且预期输出通过检查，启动器才返回成功；退出码 0 无标记仍算失败。不自动重试或结束用户现有 Mnova 会话。超时只终止本次启动的进程；如已转交旧实例，该实例仍可能继续运行，先检查日志再决定下一步。

若启动器进程以 0 退出、但本次日志明确出现 `previous instance`，说明任务可能仍在旧实例执行；启动器在本次 `--timeout` 剩余预算内等待同一个完成标记，不再启动 Mnova。超时无标记记录 `forwarded_incomplete`，先检查旧实例，不能据此自动重跑处理。没有转交证据的脚本错误仍立即报告。

## Mac 启动故障与 GUI 回退

遇到 SIGABRT 等原生崩溃时，记录当前安装版本、程序架构、退出码和日志。仅凭 abort 信息不能判断是系统服务、转译、许可、Qt 或数据导致；需要完整触发线程堆栈定位。

处理原则：

1. 有同一环境崩溃证据时停止重复 doctor/无界面运行；首次执行失败也只记录一次，不自动循环重试。启动器对负退出码保存 `native_crash` 和原值，避免把崩溃当作普通脚本错误或成功。已有输出也不能覆盖崩溃状态。
2. Mac 子进程默认移除继承的 `QT_PLUGIN_PATH`、`QT_QPA_PLATFORM_PLUGIN_PATH`、`QT_QPA_PLATFORM`，让 Mnova 使用自身部署；仅记录移除的变量名，不修改父进程或系统环境，不强设 offscreen/minimal。这是避免外部 Qt 覆盖的措施，不保证修复所有原生崩溃。Qt 官方说明 [插件路径可干扰其他 Qt 安装](https://doc.qt.io/qt-6/deployment-plugins.html)，[QPA 环境变量可覆盖默认平台](https://doc.qt.io/qt-6/qpa.html)。
3. 若正常 GUI 可以启动，准备同一原生 `.qs`，不再通过失败的命令行预检。以下命令只生成 UTF-8 BOM 脚本和清单，不启动程序、不处理数据、不宣称执行成功：

```sh
python3 scripts/mnova_runner.py prepare-gui --script "/path/to/process.qs" --function processSpectrum --run-dir "/path/to/run-logs" --expect "/path/to/result.mnova"
```

4. 在已安装且正常的 Mnova GUI 的脚本编辑器中加载输出目录的 `wrapped.qs`，选择函数 `_mnovaRunnerEntry` 执行。由当前可用、受支持的 GUI 工具操作；没有该能力时给用户明确待执行步骤。任务已授权且有工具能力时继续执行；无能力时不宣称完成。
5. `prepared_not_executed` 不能改称已处理。每次准备生成新目录，wrapper 在函数执行开始时删除旧完成标记，防止 GUI 重跑失败后遗留上次成功状态；脚本有语法/加载错误而入口未执行时仍需检查文件更新时间，不能只看旧标记，修改后应重新 prepare。执行后需确认本次 `completed.txt`、目标文件更新和原生对象，独立重新打开并核验。GUI 手工完成等效处理时没有标记也可以人工核验，但须明确实际执行方式，不能伪造标记。无界面已崩溃时在正常 GUI 内重新打开和渲染，避免验收阶段再次触发崩溃。
6. GUI 也失败时保留诊断、脚本和输出状态，明确未完成；不删许可、改签名或强制转译。进一步定位读取完整触发线程堆栈及日志。

## 新安装的能力核验

在当前版本先验证 File/TextStream、脚本编码、保存、重新读取和页面渲染。程序架构、静态资源检查及其他环境的成功不能代替这些步骤；字体和版式按 [显示规范](display-style.md) 与 [版式指南](layout-guide.md) 检查。

官方资料：[Mnova 脚本入门](https://mestrelab.com/starting-guides/how-to-get-started-with-mnova-scripts.html)；[命令行脚本说明](https://www.mestrelabcn.com/Manual_HTML_Mnova_15/new_item.htm)。文档和参数按用户实际版本核对。

## 元数据兼容

某些 bundle 的 plist XML 属性引号含字面 `\"`；启动器仅对此已识别的 XML 头形式在内存中处理转义，不修改厂商文件。其他损坏元数据明确报错。原生脚本资源路径和 API 使用见 [mnova-execution.md](mnova-execution.md)，不要求每个版本都带相同文档目录。
