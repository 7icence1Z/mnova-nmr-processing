# 无界面脚本生成与核验 .mnova

## 程序与职责

优先使用原生脚本生成 `.mnova`。人工解析指逐区检查谱点和图像后做选择，再写入原生对象。Mac 无界面启动崩溃时允许在正常 GUI 会话执行同一脚本或进行等效原生操作；不得为了“纯脚本”反复触发崩溃，也不得在没有实际执行的情况下报告完成。

| 程序 / 库 | 用途 |
| --- | --- |
| 已安装并激活的 `MestReNova.exe` | 以 `--nogui` 运行原生 QtScript；FID 导入、傅里叶变换及预处理、定标、原生峰/积分/多重峰/结构/文字对象、排版、`.mnova` 保存与重新读取、页面 PNG 渲染、可选 PDF 导出 |
| Mnova 的 QtScript `.qs` | 调用安装目录 `documents/scripts/` 所载 API；不是 Node.js 脚本，也不能独立于 Mnova 运行 |
| Python 3 标准库 `subprocess`、`pathlib` | 无界面启动 Mnova、传递参数、设置工作目录与超时、收集退出码、检查日志和输出文件 |
| Python `numpy` | 读取 Mnova 导出的 ppm / 强度数据，辅助核查谱区、积分比例和可靠谱线间距；不是全谱自动解析的替代 |
| Python `Pillow`（或已有的绘图库） | 将谱点绘成全谱及局部 PNG，供逐区判断；不代替 Mnova 保存原生文档 |
| 可用的本地图像查看工具 | 检查上述 PNG 和 Mnova 页面渲染，确认峰形及版式；不控制 Mnova GUI |

优先使用环境已有 Python 与库；记录本次使用的可执行文件路径和必要依赖。不要把本机路径写成通用安装要求。

## 命令行入口

优先使用 [跨平台启动器](cross-platform.md) 统一安装发现、参数数组、编码和运行日志。下述 `MestReNova.exe` 是 Windows 程序名；macOS 由启动器读取 `.app` 的 Info.plist 来解析内部程序。现有原生处理与版式 API 保持不变，Mac 仍需实际验证当前版本。

在 Windows / Mnova 14.0.0-23239 已实测 FID 导入、预处理、人工定义分析对象、保存、重新读取及页面渲染；新增启动器在该安装上完成了参数检测和真实小型脚本运行。Mac 17.0.1-41952 仅完成 DMG 静态检查及 bundle 解析测试，完整运行尚未实机验收。其他安装先用启动器 `doctor` 核对当前版本参数；Windows 文档/示例位于安装目录 `documents/scripts/` 和 `examples/scripts/`，已检查的 Mac 包示例位于 `Contents/Resources/scripts/examples/`，没有独立的前述 HTML 文档路径。按当前版本随附示例和帮助核对 API。

```text
MestReNova.exe --nogui --wait --logfile run.log --sf processSpectrum process.qs
```

- `--sf` 传递脚本中定义的函数名，例如 `processSpectrum`，无参数调用不加 `()`；`processSpectrum()` 在实测版本中被当成完整函数名，报找不到函数。
- `.qs` 文件作为位置参数加载；不要猜测 `--script`。
- 将进程工作目录设为 Mnova 安装目录。Python 使用参数数组执行，不拼接 shell 命令；中文与空格路径作为完整参数传入。设置合理超时，超时后检查本次进程和日志，再决定是否重试，避免并发调用。
- 退出码 0 不能证明成功：实测脚本异常仍可能以 0 退出；前次实例未退出也可能出现“started at previous instance”。检查本次日志、输出更新时间、重新读取结果，遇到转交旧实例时确认实际脚本是否完成。
- 无界面入口原生崩溃时保留诊断并停止自动重试。GUI 正常时可用 `prepare-gui` 准备原生脚本，随后通过当前可用的受支持 GUI 工具或用户正常会话执行；准备不等于执行。无 GUI 能力时说明待执行步骤，不能伪造 `.mnova` 或成功结果。具体见 [cross-platform.md](cross-platform.md)。

## 两阶段处理与独立验收

1. **导入、预处理及导出谱点。** 从完整实验目录的 FID 重新导入，不复制示例成品谱图。使用 `NMRSpectrum`、`NMRProcessing` 应用自动相位和基线，关闭全谱自动拾峰；保留其他合理导入处理设置。通过 `spec.real("all")` 取得强度，用 `spec.unitsToUnits("pt", "ppm", i, 1)` 取得对应化学位移，以 `File` / `TextStream` 写出 TSV。Python 绘制全谱、信号区和必要的细节区，检查峰形与基线。
2. **逐区判断并写回。** 根据当前谱图确认定标峰、可靠谱线、积分边界及多重峰模式，再通过 QtScript 显式设置。定标后所有坐标使用同一坐标系。用 `Peak` / `Peaks` 写人工峰标，`Integral(spec, SpectrumRegion(...), false)` / `Integrals` 写积分，`Multiplet` / `Multiplets` 写峰组。清晰 d 等用参与谱线计算 J；重叠区可为 m，不补造裂分。报告括号与 multiplet 名称均直接写化学归属，不使用字母代码和独立释义表。
3. **结构与排版。** 可从用户提供且确认结构的文件读取原生 `Molecule`，或用当前 API 导入经确认的结构。已有示例可提供结构对象，不能提供未经复核的峰位或积分。用 `page.cloneItems(...)` 复制原生对象，用 `draw.text(..., true)` 创建可编辑文字；显示主谱、局部放大、结构、直接归属和轴下积分。
4. **保存。** `serialization.save(outputPath, "mnova")` 保存原生文档；该 API 未声明返回布尔值，实测会返回空值，不写 `if (!serialization.save(...))` 来判断失败。由调用端查日志、文件状态及重新读取结果。只有用户要求时才执行 `serialization.save(pdfPath, "pdf")`。
5. **独立重新打开核验。** 在正常执行路径中 `serialization.open(outputPath)`，枚举原生谱图、积分、多重峰、结构和文字对象；核对范围、频率、积分归一化、峰位置、multiplet 名称及报告内容。对主谱及所有 Expansion 读回 [显示设置](display-style.md) 属性。用 `page.toPixmap(dpi).save(pngPath, "PNG", -1)` 或实际 GUI/PDF 渲染完整页面，检查裁切、遮挡与可读性；必要时修改后重新核验。无界面正常时独立调用；已知崩溃时使用正常 GUI 会话，不再触发失败模式。PNG 是核验材料，不能代替 `.mnova`。

## 已验证的实现细节

- 显示预设由 `scripts/display_style.qs` 显式应用到主谱和每个 Expansion：关闭背景网格、纵轴及 `multiplets.*` 的标记/积分显示，保留普通 `integrals.*` 与 Peak Picking。隐藏原生多重峰显示层不删除对象；细边框与背景网格分开控制。完整规则和验收见 [display-style.md](display-style.md)。属性来源已查 Mnova 14 随附帮助；在 Mac 当前版本仍需读回和渲染核验。

- 自动处理使用过 `PC[1].Method = "Global"`、`PC[1].InitMode = "InitZero"`、`BC[1].Apply = true`、`BC[1].algorithm = "Bernstein"`、`PP.Apply = false`。这是可查阅的实测配置；其他谱图仍须检查效果，不固定频率、溶剂、定标值或积分区间。
- 单一归一化锚点：`integrals.normValue = anchor.integralValue() / anchorHydrogenCount`，其余积分读取 `integralValue(integrals.normValue)`。若用可编辑文字呈现轴下积分，文字从当前实测积分生成，不硬编码或独立强制为理论整数；每次重处理后同步更新。
- `page.left` / `page.top` 可以非零。创建对象时先按页面内相对位置设置几何，完成后仅一次 `item.translate(page.left, page.top)`；或从一开始使用页面绝对坐标，不能两种方式叠加。`item.left` / `top` setter 会改变边界和尺寸，不能靠逐项加偏移来平移已排好的对象。
- `spec.horzZoom(14, -1, "ppm")` 设置主谱范围；`getScaleLimits()` 可能按最小值/最大值返回，需核对实际渲染左高右低。`page.cloneItems([spec])` 可创建局部放大，分析数据保持一致。
- 峰标位置按渲染选择：`peaks.position = "Top"` 可将标签放在上方独立区域；`"PeakGroups"` 可贴近峰组，但需检查是否与积分曲线交叉，不能固定认为其中一种总是更清楚。`grid.showframe = true` 可明确放大图边界。
- 优先显示原生积分标签：`integrals.label.show = true`、`integrals.label.position = "Segment"`。通过 `vertZoom(...)` 的负下限为基线以下的积分段和数字留出空间，上限兼顾峰高、积分曲线和标签。二苄叉丙酮的改进版用过主谱下限约 -1800、上限约 `realMax * 1.4`；这些是该数据强度单位下的样例，不能直接当作其他样品默认值。
- `integrals.curve.margin`、`integrals.curve.maxheight` 可调整积分曲线区域，需与峰标一起渲染检查。原生积分标签、刻度和峰线不能重叠；保留主谱的积分和必要峰标，不能仅显示放大图标签。详细要求见 [example-layout.md](example-layout.md)。
- 主谱曲线与峰标间距过大时，调整 `integrals.curve.margin` 和 `integrals.curve.maxheight`，让最高的绿色积分曲线位于峰标下缘附近；二苄叉丙酮本次版式使用过 margin = 12、maxheight = 8，其他页面需按实际渲染调整；这两个值属于显示参数，不改变积分归一化。纵轴先按当前数据最高峰和弱峰选择，避免照抄样例的 `realMax` 倍数。低场/高场信号与页面对象重叠时，先平移相关对象，再视需要适度提高 `vertZoom` 上限；重渲染确认弱峰仍清楚。
- 多重峰报告使用显式富文本样式，例如 `draw.text('<span style="font-family:Times New Roman; font-size:11pt; font-weight:normal; font-style:normal;"><sup>1</sup>H NMR (400 MHz, CDCl<sub>3</sub>) δ ... (<i>J</i> = ... Hz, ...)</span>', true)`；示例频率和溶剂只是格式展示，实际文本从当前实验生成。中文片段单独指定可用的中文字体，保持左对齐。脚本包含中文或 δ 时，本机 Mnova 14 已使用 UTF-8 带 BOM 的 `.qs` 正确加载；无 BOM 时需验证编码，不能只检查控制台文字而忽略原生页面渲染。

## 交付时记录

交付 `.mnova` 路径及实际使用的频率、溶剂、定标依据。保留本次 `.qs`、调用脚本或命令、日志和核验图，说明每一步使用了哪些程序，以及已验证的结果。化学解析依赖当前数据逐区判断；一次样品成功不代表其他版本或所有样品已通过批处理验证。
