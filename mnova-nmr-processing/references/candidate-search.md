# 未知结构候选检索接口

仅在用户明确要求推测并提供有效线索时读取本文件。已知结构验证按 [structure-policy.md](structure-policy.md) 定向查实验谱或文献，不调用未知候选搜索。

## 请求与运行

`scripts/nmrshiftdb_search.py` 使用 Python 标准库。请求 JSON 包含：

| 字段 | 要求 |
| --- | --- |
| `mode` | `guess_structure` |
| `clues` | 至少一项有效线索；可含 `molecular_formula`、反应背景等 |
| `nucleus` | 明确为 `1H` 或 `13C` |
| `signals` | 人工复核的信号组列表，每项含数值 `delta`；可保留 `relative_integral` 用于人工比较 |
| `tolerance_ppm` | 为当前核种、定标、溶剂和数据质量选择的正数容差 |
| `search_mode` | `whole` 或 `sub`，默认 `whole` |
| `solvent` | 可记录当前溶剂供复核；不意味着接口自动按溶剂筛选 |

分子式可选，但须由用户或独立实验支持，不能从猜测结构反向强加。无分子式时至少提供两个复核位移及其他有效线索。使用核环境的中心位移，不将每条裂分线、溶剂、噪声或卫星峰算作独立信号。未分辨包络仅作粗略特征并保留局限；相对积分不是 API 的峰高强度。

```sh
python3 scripts/nmrshiftdb_search.py --request "/path/to/query.json" --output-dir "/path/to/search-run" --limit 5
```

命令在安装后的 skill 目录执行；Windows 可用 `python`，macOS 使用已安装的 Python 3.9+ 的 `python3`。脚本直接通过 HTTPS 检索，不依赖 Mnova 进程、浏览器自动化或平台专用命令；支持带空格、中文的路径及 UTF-8（可带 BOM）请求文件。macOS 的 Mnova 原生处理仍按跨平台执行说明检查。

脚本检查请求模式和线索，但人类是否要求推测由调用代理判断。完整响应留在文件中，控制台默认只显示前 5 个候选。

## 接口与结果解释

依据官方 [OpenAPI 源码](https://svn.code.sf.net/p/nmrshiftdb2/code/trunk/nmrshiftdb2/api-docs/rest.yaml) 和 [自动化说明](https://sourceforge.net/p/nmrshiftdb2/wiki/AutomationInterfaces/)，只读检索，不提交记录：

- 有分子式时用 `/doSearch/searchfield/chemical%20formula/searchstring/{formula}` 缩小候选集，在本地比较存储谱与实测位移。
- 无分子式时用 `/dereplicate/searchspectrum/{shift|list|}`，明确传 `spectrumtype` 及 `subspectrum`。服务可能返回 HTTP-200 HTML 错误页，必须验证 CML 内容。
- 保留 `response.cml`、`result.json`、请求条件及时间。`failed` 是服务或响应错误，`no_match` 是成功解析后没有分子记录。`no_usable_spectra` 表示有分子记录但无可比较的目标核种谱（如只有计算谱），`no_shift_match` 表示有可比较谱但所给容差内没有位移配对；这些状态均不能称为找到谱图匹配。`candidates_found` 仅表示至少有位移配对，不代表完整谱相符或身份确定。不因服务失败自动部署其他模型。
- `shift_coverage_score` 是本地一对一位移匹配覆盖率，不是正确概率或数据库置信度。先按覆盖率降序，再按对应谱的 `best_shift_mae_ppm` 升序截取候选；误差只统计已配对信号，不能代替覆盖率。积分、多重性、J、背景及溶剂需人工复核。
- 明确计算谱默认排除；性质证据缺失的谱标记 `provenance=unknown`，不能仅凭数据库 ID 称为实验参考。

候选支持与矛盾、身份结论和后续可选工具均按结构策略处理，不用排名覆盖实测分析。
