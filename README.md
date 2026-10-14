# Mnova NMR Processing

用于 Codex 的一维氢谱处理技能：通过已安装并激活的 MestReNova，将原始 FID 处理为可编辑的 `.mnova`，可选导出 PDF。优先使用无界面原生脚本；Mac 无界面崩溃时可在正常 GUI 会话执行原生脚本并核验。

## 安装与使用

将本仓库的 `mnova-nmr-processing` 文件夹复制到 `~/.codex/skills/`。

`tests/` 是仓库开发验证文件，不需要复制到 skills 安装目录；用户实际安装只需要 `mnova-nmr-processing/`。

Windows 和 macOS 共用 Python 3.9+ 标准库启动器。在安装后的 skill 目录运行 `python3 scripts/mnova_runner.py doctor`（Windows 可用 `python`）；在仓库根目录运行时使用 `python3 mnova-nmr-processing/scripts/mnova_runner.py doctor`。Mac 可在 `doctor` 前显式提供 `--mnova "/Applications/MestReNova.app"`，自动读取 bundle 内的可执行文件。能力检测、脚本运行和日志方式见 [跨平台执行说明](mnova-nmr-processing/references/cross-platform.md)。启动器不包含自动化学归属或通用成品生成器；具体样品的处理与核验 `.qs` 由代理按当前谱图生成。

在 Codex 中提供完整原始数据目录（Bruker 数据需保留 `fid`、`acqus` 等关联文件）、样品结构及具体要求，例如：

```text
使用 $mnova-nmr-processing 处理这个一维氢谱，保存 .mnova，并导出 PDF。
```

## 处理规则

- 主谱默认范围为 −1～14 ppm；频率和溶剂从实际数据读取。
- 主谱及所有放大图默认白色无网格背景，无多重峰标记、无多重峰积分、无纵坐标；保留普通绿色积分和蓝色峰拾取。提供 [实际显示设置脚本](mnova-nmr-processing/scripts/display_style.qs)，详见 [显示规范](mnova-nmr-processing/references/display-style.md)。
- 使用自动相位校正和自动基线校正。
- 逐区人工判断标峰、积分和多重峰，避免过度拆分未分辨的信号。
- 完成定标、积分归一化、结构归属、局部放大及解析文字。
- 在报告各信号中直接写化学归属，不使用 a/b/c/d 加单独释义。
- 保存后重新打开 `.mnova` 核验；仅在要求时导出 PDF。

Mnova 原生 QtScript 负责处理和保存，Python 辅助调用、谱点分析和绘图；人工解析通过逐区检查谱点及图像完成。程序职责、命令与验收方式见 [执行说明](mnova-nmr-processing/references/mnova-execution.md)。课程材料、原始 NMR 数据、安装包及解包内容不随仓库分发。

## 当前验证状态

| 环境 | 已验证 | 待验证 |
| --- | --- | --- |
| Windows / Mnova 14.0.0-23239 | 现有原生处理与页面渲染流程；新启动器的安装发现、参数检查和真实小型脚本运行 | 其他版本及不同样品仍需逐次验收 |
| macOS / Mnova 17.0.1-41952 | DMG 静态解包；Intel/Apple Silicon 主程序结构；实际 bundle 路径与 Info.plist 兼容解析；随附 QtScript 示例检查 | 真实 Mac 上的无界面脚本执行、许可证、保存/重新读取、字体及页面渲染 |
| macOS / Mnova 16.0.0-379276（用户反馈） | 截图显示 Intel 转译运行时发生 SIGABRT；另一张截图报告 GUI 路径完成处理 | 崩溃根因及完整成品未独立复核，不据此认定系统服务或转译是根因 |

**Mac 已完成适配与静态检查，尚未完成实机验收。** 不将 Windows 测试或安装包检查表述为 Mac 完整流程运行成功。

启动器的标准库单元测试覆盖 bundle 解析、异常 plist、路径、超时、崩溃诊断、不自动重试、GUI 脚本准备和完成/输出检查。在仓库根目录运行 `python3 -m unittest discover -s tests -v`（Windows 可用 `python`）。启动器成功只代表调用及输出检查通过，化学解析和版式仍须按 skill 核验。

无界面崩溃后先查看本次日志，不反复重启。`prepare-gui` 无需调用 Mnova 或 `--help`，只准备待 GUI 执行的脚本；状态明确为 `prepared_not_executed`。具体步骤见 [故障处理](mnova-nmr-processing/references/cross-platform.md)。

已发生启动崩溃的 Mac 可先用 `doctor --static` 读取安装版本及 Intel/ARM 文件架构，整个检查不启动 Mnova。运行器会在预检前拒绝无效输入，保留预检超时的错误输出；有旧实例转交证据时等待原任务完成，不重复启动。
