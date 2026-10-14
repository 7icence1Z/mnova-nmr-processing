# Mnova 原生处理 API 与实现注意事项

启动、日志、超时、安装发现及 GUI 回退统一按 [cross-platform.md](cross-platform.md)。本文在编写样品处理和核验 `.qs` 时读取；API 按当前安装的帮助与官方示例核对，不假定所有版本相同。

Mnova QtScript 创建并保存原生文档；Python 标准库负责启动器，已有数值/绘图库可辅助检查谱点。`.qs` 不能由 Node.js 独立运行，外部绘图也不能替代 `.mnova`。脚本资源可能位于 Windows 的 `scripts/`、`examples/scripts/` 或 Mac bundle 的 `Contents/Resources/scripts/`，以当前安装为准。

## 处理和分析对象

- 导入完整实验目录的 FID，使用 `NMRSpectrum`、`NMRProcessing` 设置预处理。当前版本支持时，可从 `PC[1].Method = "Global"`、`PC[1].InitMode = "InitZero"`、`BC[1].Apply = true`、`BC[1].algorithm = "Bernstein"`、`PP.Apply = false` 开始；效果需逐谱检查，不固定线宽、定标或区间。
- 通过 `spec.real("all")` 取强度，`spec.unitsToUnits("pt", "ppm", i, 1)` 取坐标，以 `File` / `TextStream` 导出 TSV。定标后重新导出或统一转换坐标，不能混用定标前后区间。
- 用 `Peak` / `Peaks` 写已确认的峰；`Integral(spec, SpectrumRegion(...), false)` / `Integrals` 写人工区间；`Multiplet` / `Multiplets` 写确认的峰组。选择依据见 [manual-analysis.md](manual-analysis.md)，结构归属见 [structure-policy.md](structure-policy.md)。
- 有独立氢数锚点时，`integrals.normValue = anchor.integralValue() / anchorHydrogenCount`，其余读取 `integralValue(integrals.normValue)`。无氢数依据时锚点可设相对值，报告不得加 H。显示数字来自当前实测积分，重新处理后同步，不独立强制成理论整数。

## 页面与显示

- 从当前样品确认的结构文件导入原生 `Molecule`；可以复用相同结构对象，但不能复制其他实验的谱位和积分。未知结构按结构策略保留未归属或候选状态。
- `page.cloneItems([spec])` 创建 Expansion；`spec.horzZoom(14, -1, "ppm")` 设置主谱。`getScaleLimits()` 可能按最小/最大值返回，需检查实际渲染左高右低。
- `page.left` / `page.top` 可以非零。使用页面绝对坐标，或相对排版完成后仅一次 `item.translate(page.left, page.top)`，不能两者叠加。`left` / `top` setter 可能改变尺寸，不用逐项加偏移模拟平移。
- 按 [display-style.md](display-style.md) 使用显示 helper 或等效 GUI 属性；隐藏 multiplet 显示不删对象。`peaks.position = "Top"` 或 `"PeakGroups"` 按实际页选择，避免与积分交叉。
- 原生积分标签使用 `integrals.label.position = "Segment"`；通过 `vertZoom(...)` 的负下限留出基线下空间，上限兼顾峰高和弱峰。`integrals.curve.margin` / `maxheight` 控制曲线显示区域，不改变归一化。具体布局验收见 [layout-guide.md](layout-guide.md)。
- `draw.text(..., true)` 创建可编辑富文本；报告显式设置字体和样式，内容从当前实验生成。脚本用 UTF-8 BOM，最终检查保存后的原生页面，不能仅凭控制台编码判断字形正确。

## 保存与重新读取

`serialization.save(outputPath, "mnova")` 保存原生文档；其返回值可能为空，不能用 `if (!serialization.save(...))` 判失败。由启动器查输出更新和日志，并独立 `serialization.open(outputPath)` 核验谱图、分析对象、结构/报告及显示属性。

`page.toPixmap(dpi).save(pngPath, "PNG", -1)` 可渲染核验页；正常 GUI/PDF 渲染也可用于视觉检查。PDF 仅用户要求时用 `serialization.save(pdfPath, "pdf")` 导出。文件存在或成功标记不代替原生对象和整页验收。
