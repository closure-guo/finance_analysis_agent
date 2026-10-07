# Tasks: add-chart-data-integrity

- [x] 真实银行（601818）/制造业（600519）新浪报表固化为 tests/fixtures CSV（年度行，全列）
- [x] R1 `_rename_parent_cols` 列名归一化解析 + 列位回退：复现测试红→绿（银行模板解析到真实归母列、制造业回归不变、列名损坏回退生效）
- [x] R2 `calc_profitability` 毛利率缺失→None、ROE 回退输入缺失→None：复现测试红→绿（银行 fixture 毛利率全 None、ROE ≈ 净利/平均归母权益）
- [x] R3 年度图表横轴升序（含热力图行序、仪表盘子图）：测试红→绿
- [x] R4 缺数据三级语义（热力图掩膜+占位文本、柱图 NaN 断开、增速vs股价全缺占位说明）：测试红→绿
- [x] R5 金额序列 /1e8 亿元渲染 + 数据标签同步：测试红→绿
- [x] ruff + mypy + 相关 pytest 子集全绿
- [x] 真实数据实证：601818 全链重算——ROE 2021 回归合理量级（≈9% 档，非 28%）、毛利率 None、PE_ttm 可推导（≈5.5）、归母权益 ≈ 真实归母口径
- [x] 人工验证报告落 tests/validation/（修复前后报告图表对比 + 数值对照）
- [x] openspec validate add-chart-data-integrity --strict 通过
