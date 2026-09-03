# Delta for citation-verification

## MODIFIED Requirements

### Requirement: 正文覆盖率校验（citation recall）

系统 SHALL 对最终报告 markdown 执行数字普查：提取全部数值表述（百分比/金额/倍数，归一化口径由 fixture 钉死），逐一与全部 claim 的 stated_value 在**普查容差（相对 2%，绝对值下限 0.01）**内匹配，产出 `citation_coverage = 已认领数值数 / 普查数值总数`，并作为 NUMERIC Score 上报 Langfuse。豁免清单（编号、评级刻度等）SHALL 显式声明并进 fixture。覆盖率 SHALL NOT 参与 after_citation 路由（首版只监控，低于阈值 0.8 告警）。
(Previously: 普查匹配复用校验器 0.5% 相对容差；豁免清单仅为编号/评级刻度等静态清单。)

普查匹配规则 v3（2026-09-02 人工终裁，issue #106）：
1. **模板/脚手架文本排除**：决策语义、仓位档位说明（position_size 档位/如总资金/试 探性仓位等）结构性文本区间的数值 SHALL NOT 计入普查；排除清单进 fixture。
2. **方向词符号不敏感**：数值邻近（±20 字符内）方向词（下滑/下降/增长/上升/减少/增加）时，按绝对值匹配——`下滑 10.05%` 与 claim `-10.05` 认领命中。
3. **不等式匹配**：数值带「超/约/近/低于/高于/达到」修饰时，与 claim stated_value 按阈值比较（|value − stated| ≤ 2%·|stated| 视为命中），不再要求等值。
4. **事件数字标记**：数值能匹配到 state 事件源（key_events/news 中出现的数值）时，标记 `event_covered` 而非 unmatched；事件来源数字 SHALL 允许不建数值 claim，但正文 SHALL 内联注明来源事件。

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

## ADDED Requirements

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
