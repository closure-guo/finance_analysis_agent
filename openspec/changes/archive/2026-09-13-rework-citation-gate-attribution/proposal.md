## Why

r2 专项归因（incident 026）：565 条 claim 中 39 个 FAIL 抽样无一为分析师数字写错——全部是校验器认不出正确表述（日期显示格式、季度标签、单位量级、真实列名、恒正水平量的符号校验）；98 个 UNVERIFIABLE 中 75 个是舆情文本 claim（只能数值比对）、23 个是未注册的计算型字段。`citation_pass`=「FAIL 为零」把校验器的解析债算在分析师头上，并被实验报告当作引用质量指标呈现（1/9）。

更严重的是自动处置建立在这个误读上：定向重试只盯 value_mismatch / direction_mismatch 两个桶（终裁为 100% 误报）加 coverage-gap 补 claim，分析师重写表述不变、校验结果不变，停滞判定前打满 3 轮——r2 九条 deep 分析师生成 75 次（fundamental 25 次），并在 r1 造成「好报告被解析失败的降级版覆盖」事故。

纪律：处置对象必须匹配归因桶——契约病修契约、解析病修解析器、真幻觉才修分析师；自动化处置只允许挂在人工终裁确认为真错误的桶上。

## What Changes

按杠杆排序分阶段：

- **阶段 0（立即，配置级）**：自动重试默认停用（value_mismatch / direction_mismatch / coverage-gap 三条路径），保留桶统计与 retry_targets 计算供观测；新增停滞保护「重跑后目标分析师输出不变即停」；重试准入改为「仅经代码复核确认为真错误的桶」（当前为空集）。
- **阶段 1（校验器归一）**：日期 `YYYY-MM-DD` ↔ `YYYYMMDD` 双向匹配；`quarterly_trend` 季度标签 ↔ 位置索引映射；数值比对前按 interpretation 单位词（亿/万/元）缩放，无单位词时 1e4/1e8 比值兜底并标 `unit_inferred`；报表域列名词表由 DataFrame 列动态生成，claim metric_name 与解析出的真实列名一致即判一致；指标注册 `signed` 属性，符号校验仅对有符号量生效。清零后以注入式故障演练验证门禁仍会开火。
- **阶段 2（注册表补全）**：`garp_result`、`anomalies` 等由代码从快照计算的字段注册进重算表，UNVERIFIABLE → 代码可验。
- **阶段 3（文本 claim 分型）**：不新增字段——`claim_type ∈ {entity, regulatory}` ��� `source_type = event` 的 claim 不进 FAIL=0 分母、不计覆盖缺口；加回声匹配（标题/事件子串命中即 PASS(echo)）；NLI 作第二层备选，不在本 delta 内实施。
- **阶段 4（auto-claim）**：正文数字唯一匹配 state 结构化条目时自动生成 claim 挂 field_ref，缩小覆盖缺口。
- **门禁三层分置**：阻断 = 归一后残余 FAIL（经终裁桶）= 0；警告 = coverage < 0.90 报警不阻断；跟踪 = UNVERIFIABLE 占比。`citation_minor_fail` 降级放行随之退役。
- **指标拆报**：实验报告与 trace 元数据分别输出分析师真错率、校验器误报率（归一前后差）、结构不可验占比，不再单独呈现混合的 `citation_pass`。

## Capabilities

### New Capabilities

（无——全部落在既有两个规范内）

### Modified Capabilities

- `citation-retry-policy`: 「引用校验重试降级」改为「自动重试默认停用 + 停滞保护 + 重试准入」；既有降级/轻微失败/轮次上限条款保留为重试启用时的约束。
- `citation-verification`: 新增单位量级归一、路径形态归一、有符号量限定符号校验、文本 claim 分型与回声匹配、门禁三层分置、指标拆报；「计算型声明重算注册表全覆盖」扩展到快照派生字段（garp_result / anomalies）。

## Impact

- 代码：`routing.py`（after_citation / route_to_analysts）、`nodes/citation_node.py`（分层裁决、停滞保护、拆报）、`citation.py`（归一层、signed 注册、echo 匹配、auto-claim）、`metric_vocab.py`（signed/unit 属性、动态列名）、`evals/run.py` 与 `evals/task.py`（拆报指标）、trace 元数据键。
- 提示词：分析师 prompt 的 field_ref 语法段可保持不变（归一在校验器侧）；`direction` 字段加「符号非高低」注释（随 deploy_prompts 发布）。
- 实验口径：`citation_pass` 语义变更，r1–r3 的该指标与后续不可直接比较；复盘文档 §6 与 incident 026 为基线。
- 测试：路由测试改为「默认停用」语义，既有重试测试改为显式开启标志下运行；新增注入式故障演练用例；r2 39 条 FAIL 逐条作 fixture。
