# Mnova 执行接口准备

准备阶段检查的 Windows 安装为 Mnova 14.0.23239，带 `ScriptingPlugin.dll`。仅完成安装目录、文档及官方示例的静态检查；尚未验证运行入口、许可证状态或实际作业处理。用户约定默认已激活。

其他电脑重新定位安装目录并读取当前版本的文档，不硬编码本机路径。优先查看 `documents/scripts/mnova-scripting.html`、`examples/scripts` 和 `scripts`。不要未经证据假定支持 `--script` 等命令行参数，或把 QtScript `.qs` 当作 Node.js 程序运行。

已检查的官方示例及用途：

| 相对安装目录路径 | 可查阅的接口/用途 |
| --- | --- |
| `examples/scripts/import_process_save_loop.qs` | `serialization.open(...)`；处理模板 `nmr.process(...)`；`serialization.save(path, "mnova")` 及 `"pdf"` |
| `examples/scripts/nmrProcessingTest.qs` | `NMRSpectrum`、`NMRProcessing`、相位/基线参数、人工预定义区域、`spec.reference(...)` |
| `examples/scripts/integralTest.qs` | 显式 `SpectrumRegion`、`Integral`、积分列表和 `normValue`；归一化语义要按当前 API 核对 |
| `examples/scripts/multipletTest.qs` | 显式范围构建 `Multiplet`、设置 multiplet 列表；不代表自动分类结果已可靠 |
| `examples/scripts/applyLayoutTemplateAndPrint.qs` | 应用布局模板、导出 PDF 的应用动作 |
| `examples/scripts/reportParametersAndPDF.qs` | 页面对象、文字与谱图布局、PDF 导出动作 |

这些是查阅入口，不是已测试的通用程序。实现时先确认执行方式和目标文档，检查接口返回值及实际输出；不要直接运行示例中硬编码目录的批处理循环。

脚本可以执行明确选定的积分范围、谱线和 multiplet 范围，或设置布局及保存。但 manual 解析的关键是先依据当前谱图逐区判断，禁止把示例范围或自动全谱解析当作最终结果。

若当前环境没有受支持的桌面控制，而脚本入口尚未确认，说明具体限制并提供可执行的准备材料；不得使用不可用接口或声称已检查 Mnova 窗口。需要桌面工具时按该工具当前文档和权限使用。

正式验证先在新输出目录操作，保留原始数据和示例；保存后重新打开 `.mnova` 检查编辑对象。导出 PDF 是布局验收的可选路径，不替代原生文件核验。
