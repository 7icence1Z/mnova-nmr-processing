# Mnova NMR Processing

用于 Codex 的一维氢谱处理技能：通过已安装并激活的 MestReNova，将原始 FID 处理为可编辑的 `.mnova`，可选导出 PDF。

## 安装与使用

将本仓库的 `mnova-nmr-processing` 文件夹复制到 `~/.codex/skills/`。

在 Codex 中提供完整原始数据目录（Bruker 数据需保留 `fid`、`acqus` 等关联文件）、样品结构及具体要求，例如：

```text
使用 $mnova-nmr-processing 处理这个一维氢谱，保存 .mnova，并导出 PDF。
```

## 处理规则

- 主谱默认范围为 −1～14 ppm；频率和溶剂从实际数据读取。
- 使用自动相位校正和自动基线校正。
- 逐区人工判断标峰、积分和多重峰，避免过度拆分未分辨的信号。
- 完成定标、积分归一化、结构归属、局部放大及解析文字。
- 保存后重新打开 `.mnova` 核验；仅在要求时导出 PDF。

本技能提供操作与解析指导，Mnova 脚本运行入口及完整处理流程尚未实测验证。课程材料、示例作业和原始 NMR 数据不随仓库分发。
