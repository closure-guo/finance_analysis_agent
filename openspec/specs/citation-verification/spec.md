# citation-verification Specification

## Purpose
TBD - created by archiving change fix-citation-contract-diseases. Update Purpose after archive.
## Requirements
### Requirement: 序列引用负索引语义

引用校验器对序列型 field_ref SHALL 支持负索引（-1 = 最新一期，-N = 倒数第 N 期），该语义与序列长度及上下文裁剪窗口解耦。技术指标 context 的窗口说明 SHALL 明示负索引约定（"field_ref 引用序列值时用负索引：-1=最新一期"）。正索引按底层序列原位解析（legacy 语义不变）。

#### Scenario: 负索引解析为最新值

- GIVEN state 中某指标序列为升序时间序列且任意长度
- WHEN claim 的 field_ref 以 `-1` 索引该序列（如 `technical_indicators.MA.5.-1`）
- THEN 校验器 SHALL 取序列最后一个元素作为 ground truth

#### Scenario: 裁剪窗口变更不影响校验语义

- GIVEN 分析师 context 的序列裁剪窗口从 60 期调整为任意值
- WHEN LLM 按负索引约定引用序列值
- THEN 校验结果 SHALL 不因窗口变更而改变（负索引与长度无关）

### Requirement: 上下文与校验单一词表

分析师 context 的数据段标题 SHALL 内联标注对应 state 英文键（如「利润表（income_statement，近3年）」），使 LLM 生成的 field_ref 与校验器解析的键天然同源；校验器 SHALL NOT 维护中文标签映射表。引用校验器 SHALL 支持 DataFrame 的「行键.列名」两段解析（行键按单元格值匹配，列名须为真实列）与 `[N]` 括号索引展开。

#### Scenario: 英文键引用可解析

- GIVEN context 段落标题含英文 state 键标注
- WHEN LLM 以该英文键为 field_ref 根键引用数据（含 DataFrame 行键.列名与 `[N]` 括号索引）
- THEN 校验器 SHALL 按对应 state 结构解析出 ground truth

#### Scenario: 中文标签不再是可解析词表

- GIVEN field_ref 根键为未标注进 context 英文键体系的中文标签
- WHEN 校验器解析该引用
- THEN SHALL 按不可路径处理（FAIL），不静默映射

### Requirement: 数值型相对容差

数值型 claim 的 PASS 判定 SHALL 为 |delta| < 0.01 或相对误差 < 0.5%（与计算型容差对齐），消除大数量级数值的假阴性。(Previously: data-ordering-citation-contract（archive）约定校验算法不变，数值型为绝对容差 0.01)

#### Scenario: 亿元级数值四舍五入通过

- GIVEN ground truth 为 1,038,756,658.94 量级的数值
- WHEN stated_value 与其相差 0.5（远小于 0.5% 相对误差）
- THEN 校验 SHALL PASS

#### Scenario: 显著偏离仍失败

- GIVEN ground truth 为任意数值
- WHEN stated_value 相对误差 ≥ 0.5% 且绝对差 ≥ 0.01
- THEN 校验 SHALL FAIL

### Requirement: 计算型声明重算注册表全覆盖

计算型 claim 的重算注册表 SHALL 覆盖 `metrics/` 模块的全部纯函数指标族（偿债、盈利、运营、现金流、杜邦、技术指标、风控指标），每个注册根键 SHALL 有独立的重算 fixture 测试（从原始报表数据重算，不依赖 LLM、不调外部接口）。未注册根键的计算型 claim SHALL 判 UNVERIFIABLE，且 SHALL 计入覆盖缺口指标供覆盖率审计。

#### Scenario: 已注册指标重算通过

- **GIVEN** Agent 报告含计算型 claim（如 `solvency_metrics.资产负债率.2024`），其根键已注册
- **WHEN** 执行校验
- **THEN** 系统 SHALL 从 state 原始数据经对应纯函数重算 ground-truth，按相对容差 0.5% 判定 PASS/FAIL

#### Scenario: 未注册根键显式降级

- **WHEN** 计算型 claim 的根键未在注册表中
- **THEN** 校验结果 SHALL 为 UNVERIFIABLE
- **AND** 该事件 SHALL 计入覆盖缺口计数，SHALL NOT 静默等同于 FAIL 或被忽略

#### Scenario: 容差语义不回归

- **WHEN** 注册表扩展后执行任意校验
- **THEN** 数值容差（绝对 0.01 / 相对 0.5%）与三态裁决（PASS/FAIL/UNVERIFIABLE）语义 SHALL 与既有契约一致

### Requirement: UNVERIFIABLE 占比监控

系统 SHALL 在每次引用校验完成后向 Langfuse 上报 Score `citation_unverifiable_ratio`（UNVERIFIABLE 占全部 claim 比例），关联 `langfuse_trace_id`。该指标 SHALL 作为数据层退化（数据源接口变更、事件管线降级、注册表覆盖缺口扩大）的先行监控信号。

#### Scenario: 占比上报

- **WHEN** citation_node 完成一次批量校验
- **THEN** 系统 SHALL 上报 `citation_unverifiable_ratio`（0-1 浮点）至 Langfuse，与既有 `citation_pass` 并列
- **AND** Langfuse 不可用时 SHALL 记 WARN 且不阻断业务管线

#### Scenario: 占比突升告警

- **GIVEN** `citation_unverifiable_ratio` 的滚动均值较基线上升超过阈值（默认 +10pp，可配置）
- **WHEN** 监控任务检测到突升
- **THEN** 系统 SHALL 产生告警记录，提示排查数据层或注册表覆盖缺口

### Requirement: context 数据形态语义声明

系统 SHALL 在构建分析师 context 时，为每个序列/数组数据块注入机器生成的语义头，显式声明：排序方向（升序/降序）、最新期定位语义（如 index -1 = 最新交易日及其日期）、序列长度。语义头由代码依据 state 实际数据形态生成，SHALL NOT 依赖 prompt 自然语言要求作为主要防线。LLM 在 context 中见到的数据形态语义 SHALL 与校验器解析语义一致。

#### Scenario: 序列块带语义头

- **WHEN** 构建含时间序列的分析师 context（technical/macro/fundamental）
- **THEN** 每个序列块 SHALL 附语义头（如"升序，index -1 = 最新交易日 2026-08-28，共 60 期"）
- **AND** 语义头内容与 state 中该序列的实际排序一致

#### Scenario: 期次错位不重现

- **GIVEN** 类似中际旭创的暴涨标的
- **WHEN** 技术分析师产出技术形态叙事
- **THEN** 叙事引用的期次 SHALL 与 state 最新期一致（不产生"窗口首元素当最新"的镜像叙事）

### Requirement: 术语与期次一致性校验

Claim SHALL 扩展 `metric_name`（指标枚举，含中文别名到规范键映射）与 `period` 字段。校验器 SHALL 校验：(a) `metric_name` 的规范键等于 field_ref 末端键；(b) `period` 与 field_ref 解析出的期间一致。不一致判 FAIL 并归入独立桶（semantic_term_mismatch / semantic_period_mismatch）。字段为 None（旧数据或未填）时 SHALL 跳过检查并计入覆盖缺口，SHALL NOT 静默 PASS。metric_name 已申报但词表无对应规范键（词表外）时 SHALL 同样跳过术语检查并计入覆盖缺口——state 指标段空间开放（报表行名/dupont/health_score/garp 等），词表不可闭合，词表外判 FAIL 经三标的冒烟实证全为误报（2026-09-01）。

#### Scenario: 术语张冠李戴被拦截

- **GIVEN** claim 的 field_ref 指向 `profitability_metrics.毛利率.2024`，metric_name 为"净利率"
- **WHEN** 执行校验
- **THEN** 判 FAIL，桶为 semantic_term_mismatch（即使数值与真值一致）

#### Scenario: 缺省字段显式降级

- **WHEN** claim 缺 metric_name/period（旧格式）
- **THEN** 跳过对应检查，计入覆盖缺口计数，其余检查照常

#### Scenario: 词表外术语显式降级

- **GIVEN** claim 申报了 metric_name，但词表无其规范键（如 "健康度评分" 之于 `health_score.total`）
- **WHEN** 执行术语检查
- **THEN** 跳过术语检查，计入覆盖缺口计数，SHALL NOT 判 FAIL；值级/期次/内部一致性检查照常

### Requirement: claim 内部一致性校验

校验器 SHALL 校验 claim 内部一致性：(a) `stated_value` 经归一化（剥离"约/接近/%"等修饰与单位）后可在 `interpretation` 中匹配到对应数值表述；(b) interpretation 中的方向词（增长/上升/改善 vs 下降/恶化）不与数值 delta 符号矛盾。不一致判 FAIL，桶为 internal_inconsistency。

#### Scenario: 数值两张皮被拦截

- **GIVEN** claim 的 stated_value 为 45.2，interpretation 写"毛利率约 30%"
- **WHEN** 执行内部一致性检查
- **THEN** 判 FAIL，桶为 internal_inconsistency

#### Scenario: 方向词矛盾被拦截

- **GIVEN** claim 断言指标变化，interpretation 含"大幅增长"，而数值 delta 为负
- **THEN** 判 FAIL，桶为 internal_inconsistency

### Requirement: 正文覆盖率校验（citation recall）

系统 SHALL 对最终报告 markdown 执行数字普查：提取全部数值表述（百分比/金额/倍数，归一化口径由 fixture 钉死），逐一与全部 claim 的 stated_value 在**普查容差（相对 2%，绝对值下限 0.01）**内匹配，产出 `citation_coverage = 已认领数值数 / 普查数值总数`，并作为 NUMERIC Score 上报 Langfuse。豁免清单（编号、评级刻度等）SHALL 显式声明并进 fixture。覆盖率 SHALL NOT 参与 after_citation 路由（首版只监控，低于阈值 0.8 告警）。
(Previously: 普查匹配复用校验器 0.5% 相对容差；豁免清单仅为编号/评级刻度等静态清单。)

普查匹配规则 v3（2026-09-02 人工终裁，issue #106）：
1. **模板/脚手架文本排除**：决策语义、仓位档位说明（position_size 档位/如总资金/试 探性仓位等）结构性文本区间的数值 SHALL NOT 计入普查；排除清单进 fixture。
2. **方向词符号不敏感**：数值邻近（±20 字符内）方向词（下滑/下降/增长/上升/减少/增加）时，按绝对值匹配——`下滑 10.05%` 与 claim `-10.05` 认领命中。
3. **不等式匹配**：数值带「超/约/近/低于/高于/达到」修饰时，与 claim stated_value 按阈值比较（|value − stated| ≤ 2%·|stated| 视为命中），不再要求等值。
4. **事件数字标记**：数值能匹配到 state 事件源（key_events/news 中出现的数值）时，标记 `event_covered` 而非 unmatched；事件来源数字 SHALL 允许不建数值 claim，但正文 SHALL 内联注明来源事件。

#### Scenario: 黑数字暴露

- **GIVEN** 报告正文含数值"营收 10.39 亿"，但无任何 claim 的 stated_value 与其匹配
- **WHEN** 执行数字普查
- **THEN** 该数值计为未认领，`citation_coverage` 相应降低
- **AND** 低于阈值时产生告警记录，不阻断报告产出

#### Scenario: 方向词符号认领
- **GIVEN** 报告正文含「净利率下滑 10.05%」，claim stated_value = -10.05，字段可校验
- **WHEN** 执行数字普查
- **THEN** 该数值按绝对值与 -10.05 匹配，计为已认领
- **AND** 不再因符号相反计为黑数字

#### Scenario: 阈值式复述认领
- **GIVEN** 报告正文含「ROE 超 30%」，claim stated_value = 32.53
- **WHEN** 执行数字普查
- **THEN** |30 − 32.53| ≤ 2%·32.53 判定命中，计为已认领

#### Scenario: 脚手架文本不计普查
- **GIVEN** 报告含 position_size 档位说明「light=试探性仓位（如总资金 10-20%）」
- **WHEN** 执行数字普查
- **THEN** 该区间数值（10%、20%）不计入普查总数

#### Scenario: 事件数字豁免
- **GIVEN** 报告引用新闻事件「出厂价由 969 元上调至 1169 元」，且该数值出现在 state 事件源中
- **WHEN** 执行数字普查
- **THEN** 标记 `event_covered`，不计入 unmatched
- **AND** 正文未内联注明来源事件时，报告 SHALL 记录提示

### Requirement: 校验失败按桶分流与定向重试

after_citation 路由 SHALL 按 FAIL 桶分流：(a) 值级 FAIL（value_mismatch，ground_truth 存在且超容差）触发**定向重试**——仅重跑产出该 claim 的分析师节点，重试上下文 SHALL 附失败 claim 明细与 ground_truth；(b) 格式/契约类 FAIL（路径不可解析、术语/期次/内部不一致）SHALL NOT 触发重试，记为 incident 候选；(c) UNVERIFIABLE 不触发重试。重试上限（iteration_count < 3）语义不变；重跑后该分析师全部 claim SHALL 重新校验。

#### Scenario: 值级 FAIL 定向重跑

- **GIVEN** 基本面分析师 1 条 claim 值级 FAIL，其余分析师全部 PASS
- **WHEN** 路由触发重试
- **THEN** 仅基本面分析师重跑（附失败明细与 ground_truth），其余分析师结果复用
- **AND** 重跑后其全部 claim 重新校验

#### Scenario: 格式类 FAIL 不重试

- **WHEN** FAIL 桶为 semantic_term_mismatch / path_unresolvable / internal_inconsistency
- **THEN** 不触发分析师重跑，记录 incident 候选并放行（flag 语义）

### Requirement: state anomalies 自动补登记

系统 SHALL 在引用校验前执行自动补登记：对正文数值与 state 的 `growth_rates`（含 anomalies 的 |growth|>0.5 子集，也含非 anomaly 增速）做**双条件共现匹配**——① 数值与 `growth_rates.{dim}.{metric}` 的整数百分比渲染（`:.0%`）按**取整感知容差**（≤ 0.5 个百分点）匹配；② 指标名与数值出现在同一句/段落。双条件满足时 SHALL 自动生成 claim，field_ref **SHALL 指向结构化真值**（`growth_rates.{dim}.{metric}`），渲染字符串 SHALL 仅用于定位、不用于验证（禁止"字符串验字符串"）。不满足任一条件的数值 SHALL 保持 unmatched 走原流程。自动补登记的 claim SHALL 与人工申报 claim 走完全相同的校验路径（容差/桶/重试语义不变）。

#### Scenario: anomalies 数值自动补登记
- **GIVEN** state 含 anomaly「solvency.净债务/EBITDA: 变化率-368%」，growth_rates.solvency.净债务/EBITDA = -3.676（即 -367.6%）
- **AND** 报告正文同句含「净债务/EBITDA 变化 -368%」
- **WHEN** 执行自动补登记
- **THEN** 生成 claim，field_ref = growth_rates.solvency.净债务/EBITDA，stated_value = -3.68
- **AND** 取整感知容差（0.5 个百分点）内与真值 -3.676 匹配，校验 PASS

#### Scenario: 指标名不共现不补登记
- **GIVEN** 正文某处单独出现「-368%」，同句无任何 anomaly 指标名
- **WHEN** 执行自动补登记
- **THEN** 不生成 claim，数值保持 unmatched 走原流程

#### Scenario: 编造数字不被洗白
- **GIVEN** 正文含「账上资金 1400 亿」，state 无对应数值/指标名共现
- **WHEN** 执行自动补登记
- **THEN** 不生成 claim，保持 unmatched → 进入 reject/人工复核
- **AND** 验证标准与人工申报 claim 完全一致，不因补登记而降级

### Requirement: comparative 基期值双端申报与校验

系统 SHALL 要求 comparative（同比/环比/对比）claim 声明双端数值：当期 `stated_value` + 基期 `stated_value_b`（field_ref_b 指向基期字段）。校验器 SHALL 对基期值与当期值使用相同的容差语义分别校验；未申报基期的 comparative claim SHALL 判 FAIL 并记录。prompt 侧 SHALL 强制比较值申报纪律（当前值 + 基期值 + 对应 field_ref/field_ref_b），改动后须经 prompt 发布流程。

#### Scenario: 基期值裸奔被拦截
- **GIVEN** 报告叙述「2025 净利率 19.07%，较 2024 年 21.93% 下滑」，claim 仅申报 2025 值（stated_value=19.07）
- **WHEN** 校验 comparative claim
- **THEN** 判 FAIL，原因：comparative 未申报基期 stated_value_b
- **AND** 引导 LLM 补申报 2024 基期（21.93）与 field_ref_b

### Requirement: 增速类计算值补登记（D2 吸收）

系统 SHALL 对「正文增速数值 + 增速指标名共现」执行补登记：`growth_rates` 中全部指标（含非 anomaly 的 |growth|≤0.5）按 D2 双条件补登记为 numerical claim（field_ref = `growth_rates.{dim}.{metric}`），取整感知容差验证。该机制覆盖「FCF 同比增长 96.6%」类可重算增速数字，即使未触发 anomaly 也补。不可定位结构化真值的数值 SHALL 不补登记，保持 unmatched。

#### Scenario: 非 anomaly 增速补登记
- **GIVEN** 正文含「FCF 同比增长 96.6%」，growth_rates.cashflow.FCF = 0.966（|growth|>0.5 会触发 anomaly，但补登记不依赖 anomaly 存在）
- **WHEN** 执行增速补登记
- **THEN** 生成 claim，field_ref = growth_rates.cashflow.FCF，stated_value = 0.97
- **AND** 0.5pp 取整容差内与真值 0.966 匹配，标准校验 PASS

### Requirement: 覆盖率缺口打回补 claim（coverage 闭环最后一公里）

系统 SHALL 在覆盖率普查产出 unmatched（D2/D4 自动补登记与 D5 事件豁免之后仍未被认领的数字）时，将缺口反馈回正文来源分析师节点做**局部补证**：反馈 SHALL 携带未认领数字（原文 + 解析值），提示分析师「补建对应 claim 或删除正文数字」；补证后 SHALL 重新校验与普查。打回上限 SHALL 与既有 citation 重试共享迭代上限（<3），停滞降级语义不变；纯评论性/无状态源数字（非硬数据）SHALL 不触发打回（属可接受口径）。

#### Scenario: 无来源数字打回补证
- **GIVEN** 正文含「账上资金超过 1400 亿元」，D2/D4 无法自动补登记（state 无对应真值），D5 不豁免
- **WHEN** 覆盖率普查
- **THEN** 将该数字加入打回反馈，定向重跑来源分析师
- **AND** 分析师补建货币资金 claim 或删除该正文数字，复验后 unmatched 消除

