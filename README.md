# Mnova NMR Processing

用于 Codex 的一维氢谱处理技能：通过已安装并激活的 MestReNova，将原始 FID 处理为可编辑的 `.mnova`，可选导出 PDF。优先使用无界面原生脚本；Mac 无界面崩溃时可在正常 GUI 会话执行原生脚本并核验。

## 安装与使用

将本仓库的 `mnova-nmr-processing` 文件夹复制到 `~/.codex/skills/`，或向 Codex 发送以下信息：

```test
帮我从 https://github.com/7icence1Z/mnova-nmr-processing 安装为全局skill。
```

`tests/` 是仓库开发验证文件，不需要复制到 skills 安装目录；用户实际安装只需要 `mnova-nmr-processing/`。

Windows 和 macOS 共用 Python 3.9+ 标准库启动器。在安装后的 skill 目录运行 `python3 scripts/mnova_runner.py doctor`（Windows 可用 `python`）；在仓库根目录运行时使用 `python3 mnova-nmr-processing/scripts/mnova_runner.py doctor`。Mac 可在 `doctor` 前显式提供 `--mnova "/Applications/MestReNova.app"`，自动读取 bundle 内的可执行文件。能力检测、脚本运行和日志方式见 [跨平台执行说明](mnova-nmr-processing/references/cross-platform.md)。启动器不包含自动化学归属或通用成品生成器；具体样品的处理与核验 `.qs` 由代理按当前谱图生成。

在 Codex 中提供完整原始数据目录（Bruker 数据需保留 `fid`、`acqus` 等关联文件）和具体要求；优先提供确定的样品结构。默认解谱后验证是否与给定结构一致，用户可明确说“跳过结构验证”。例如：

```text
使用 $mnova-nmr-processing 处理这个一维氢谱，保存 .mnova，并导出 PDF。
```

结构未知时，只有用户明确要求猜测结构，才根据用户提供的分子式/质谱、反应背景、候选范围或补充 NMR 等线索调用 [nmrshiftdb2](https://nmrshiftdb.nmr.uni-koeln.de/) 自动检索。Windows/macOS 共用 Python 3.9+ 标准库脚本，不依赖浏览器自动化：有分子式时按公式取候选并本地比较位移，没有公式时尝试官方谱图检索；原始响应和精简结果分开保存。候选按位移覆盖率及配对误差排序，区分空结果、无可用参考谱、无位移匹配及服务失败。候选不是身份确证。输入、接口限制及性质核验见 [结构验证与候选推测](mnova-nmr-processing/references/structure-policy.md)。未要求推测且未提供结构时，可先处理为未归属谱图。

部署 [NMR2Struct](https://github.com/MarklandGroup/NMR2Struct)、[lucy-ng](https://github.com/steinbeck/lucy-ng) 进行检索反推均非强制依赖；常规分析、线索补充与数据库检索仍无法解决，且数据适合时才提示用户可选部署，不自动安装。

## 处理规则

- 主谱默认范围为 −1～14 ppm；频率和溶剂从实际数据读取。
- 主谱及所有放大图默认白色无网格背景，无多重峰标记、无多重峰积分、无纵坐标；保留普通绿色积分和蓝色峰拾取。提供 [实际显示设置脚本](mnova-nmr-processing/scripts/display_style.qs)，详见 [显示规范](mnova-nmr-processing/references/display-style.md)。
- 使用自动相位校正和自动基线校正。
- 逐区人工判断标峰、积分和多重峰，避免过度拆分难以分辨的信号。
- 完成定标、人工积分、局部放大及解析文字；有可靠氢数依据时归一化为 H，否则报告相对积分。结构未知时可交付未归属谱图。
- 在报告各信号中直接写化学归属。
- 所有烯烃的氢逐组核对；能确定的不同环境、固定构型或顺反关联必须标明。不能笼统合并为“烯烃 H”，也不以 m 省略可确定归属；不能仅凭位移先后强行决定构型。
- 保存后重新打开 `.mnova` 核验；仅在要求时导出 PDF。

Mnova 原生 QtScript 负责处理和保存，Python 辅助调用、谱点分析和绘图；人工解析通过逐区检查谱点及图像完成。程序职责、命令与验收方式见 [执行说明](mnova-nmr-processing/references/mnova-execution.md)。课程材料、原始 NMR 数据、安装包及解包内容不随仓库分发。

## 兼容性与开发验证

支持 Windows 和 macOS 的安装发现及脚本启动。静态安装检查或单元测试不等于当前 Mnova 版本已完成端到端验收；首次运行需确认脚本、许可证、保存/重新读取和字体渲染。Mac 完整流程仍需实机核验。

开发测试：在仓库根目录运行 `python3 -m unittest discover -s tests -v`（Windows 可用 `python`）。
