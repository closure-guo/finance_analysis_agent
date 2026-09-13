## Context

引用校验门禁（citation）自 incident 006/020/022 起经历三轮契约修复，当前形态：分析师输出结构化 claim（field_ref/stated_value/direction/metric_name/period），`citation.py` 按 field_ref 解析 state 取真值并按容差裁决 PASS/FAIL/UNVERIFIABLE；`citation_node` 汇总为 `citation_pass`（FAIL=0）、`citation_coverage`（正文数字被 claim 认领比例）、`citation_minor_fail`（轻微失败放行）；`routing.after_citation` 对 value_mismatch/direction_mismatch 桶与 coverage-gap 触发定向重跑分析师，上限 3 轮，失败率停滞提前放行。

r2 归因（docs/incidents/026）：FAIL 桶 100% 为校验器误报；重试路径 100% 打在误报桶上；`citation_pass` 被读作引用质量。incident 020 记录��同类「考卷与答案册不同源」病，本次为复发（新形态：`render_date` 显示格式、季度标签、单位量级、`direction` 符号字段）。

## Goals / Non-Goals

**Goals:**
- 立即切断建立在误归因上的自动处置（重试），并加停滞保护与准入条件
- 校验器在自身侧做确定性归一，使照抄 context 显示形态的 claim 可解析、可比对
- 门禁只阻断真错误；覆盖与不可验分别作为警告线与跟踪指标
- 指标拆报，使评审者不再把校验器误报读成分析师幻觉
- 清零后的门禁仍能对注入的真错误开火（防「全绿即失效」）

**Non-Goals:**
- 不引入 NLI / LLM 做文本 claim 语义蕴含（decision_grounding judge v6 已承担语义忠实性核对；NLI 作后续备选）
- 不改分析师 prompt 的 field_ref 语法（归一在校验器侧，避免依赖 LLM 行为变化）
- 不处理 incident 020 残量归因的回溯复核（另立项）
- 不改 decision_grounding / consistency 等 judge 维度

## Decisions

**D0 自动重试默认停用，保留计算与观测。** `routing.py` 增模块级 `CITATION_AUTO_RETRY_ENABLED = False`；`after_citation` 在停用时对任何非 PASS 状态直接 `render`，但 `citation_node` 仍计算 fail_buckets / retry_targets / fail_rates 写入 state 与 trace（观测不退化）。选择模块常量而非环境变量：这是策略决策而非部署配置，变更须经 delta，不允许运行时静默开启。

**D0.1 停滞保护按输出内容判定。** 重试启用时，`citation_node` 在触发 retry 前记录各目标分析师 `markdown` 的哈希到 `citation_retry_prev_hash`；下一轮校验若目标分析师哈希未变（重写后文本不变）→ 置 `citation_retry_no_progress=True` 立即放行，不等失败率停滞判定。

**D0.2 重试准入 = 终裁真错误桶。** `routing` 只对 `CITATION_RETRY_ADMITTED_BUCKETS`（模块常量，当前为空 frozenset）内的桶触发重试；桶进入该集合的前提是有逐条终裁记录（docs/incidents 或 tests/validation）。value_mismatch / direction_mismatch 因终裁为误报不在集合内。

**D1 归一在解析/比对层，不在 context 层。** 日期：`_resolve_field_ref` 对 DataFrame 行键匹配时同时尝试去连字符形式；季度：根键 `quarterly_trend` 且末段匹配 `\d{4}Q[1-4]` 时查 `quarters` 列表换算索引；单位：`_verify_numerical` 先从 interpretation 中定位与 stated_value 面值相同的 token 取紧邻单位词缩放（复用 `_NUMBER_PATTERN`/`_UNIT_SCALE`），无单位词时 truth/stated 比值落在 1e4/1e8 相对容差内判 PASS 并标 `unit_inferred`；有单位词且缩放后仍不匹配保持 FAIL。真值单位以数据根键注册的 `unit` 属性归一到元（akshare 各表单位需先核实并注册）。

**D1.1 词表：报表域用真实列名，指标域用规范名。** 根键为 DataFrame（三大报表、financial_indicators）时，metric_name 与解析出的列名一致即判术语一致；`metric_vocab` 补别名（归属于母公司的净利润→归母净利润 等）。语义术语核对仍对指标域生效。

**D1.2 符号校验限定有符号量。** `metric_vocab` 注册 `signed: bool`（增长率/同比环比/变动幅度/MACD 柱等为 True；指数/比率/价格/水平量为 False）；`direction` 申报只在 signed 指标上参与 sign 比对，非 signed 指标上申报 negative 记覆盖缺口不判 FAIL。prompt 中 `direction` 加「符号语义，非高低」注释。

**D2 注册表扩展到快照派生字段。** `garp_result`、`anomalies`、比率类空值字段注册进重算表（同一份 `metrics/` 代码重算）；stated_value 为字符串枚举（如 GARP failures）按集合相等比对。

**D3 文本 claim 分型用既有字段。** `claim_type ∈ {entity, regulatory}` 或 `source_type == "event"` → 不进 FAIL 分母、不计覆盖缺口；回声匹配：claim/interpretation 归一后与 `news_list[*].title` / `key_events[*]` 做子串匹配，命中 PASS(echo)，未命中 UNVERIFIABLE(text)。

**D4 auto-claim 只在唯一匹配时合成。** 正文数字（含单位缩放）在 state 结构化条目中恰有一个匹配时合成 claim（source_type=data，标 `auto=True`）；多匹配或零匹配不合成，保持覆盖缺口。

**D5 门禁三层分置。** `citation_blocked = residual_fail_count > 0`（归一后、准入桶内的 FAIL）；`citation_coverage_warn = coverage < 0.90`；`citation_unverifiable_ratio` 跟踪。`citation_pass` 保留为 `not citation_blocked` 的别名一个版本后移除；`citation_minor_fail` 退役。

**D6 拆报。** trace 元数据与实验报告输出：`analyst_true_fail_count`（残余 FAIL）、`verifier_normalized_count`（归一后由 FAIL 转 PASS 的数）、`unverifiable_text_count` / `unverifiable_unregistered_count`。

**D7 注入式故障演练。** ���试与 golden 门禁各加一条：对真实 fixture 故意改错一个数字（非单位/非格式），归一后仍必须 FAIL 且阻断。

## Risks / Trade-offs

- **清零掩盖真错**：归一放宽了比对；D7 演练 + r2 39 条 FAIL 逐条作为回归 fixture（每条注明终裁类别）对冲。
- **比值兜底误判**：无单位词时 1e4/1e8 比值窄带内的真错会被放过；概率低且 `unit_inferred` 单独统计，占比上升即回到 prompt 要求写单位。
- **重试停用后覆盖率短期不涨**：coverage 只是警告线；auto-claim（D4）是覆盖率的正道。
- **实验指标不可比**：`citation_pass` 语义变更；以 incident 026 的拆报基线为界。
- **akshare 各表单位不一致**：D1 依赖根键 `unit` 注册，注册前先用 r2/r3 数据核实每张表单位，错注册会把正确数判错——注册表进 fixture 测试。
