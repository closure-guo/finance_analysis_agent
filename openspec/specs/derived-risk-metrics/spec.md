# derived-risk-metrics Specification

## Purpose
TBD - created by archiving change deterministic-derived-metrics. Update Purpose after archive.
## Requirements
### Requirement: 派生风险指标确定性计算

buy/sell 决策通过价位校验（pass 或 corrected）后，系统 SHALL 由纯规则代码计算派生指标：止损距离百分比 `(entry−stop)/entry` 与风险收益比 `(target−entry)/(entry−stop)`，写入 state 供下游节点消费。计算 MUST NOT 经过任何 LLM 调用；除以零（stop==entry）时结果 SHALL 为空并注明原因，MUST NOT 产出无穷/NaN。

#### Scenario: buy 方案计算派生指标

- **WHEN** `trader_plan` 或 `final_trade_decision` 为 buy，entry=52.0、stop=47.8、target=60.0，价位校验通过
- **THEN** state SHALL 携带止损距离 8.08%（±渲染精度）与赔率 1.90:1，数值由上述公式对参数原值直接运算得出

#### Scenario: 除零与缺失不产出伪值

- **WHEN** stop 等于 entry，或 stop/target 缺失或为 0
- **THEN** 对应派生指标 SHALL 为空（None），state 中注明缺失原因，MUST NOT 渲染或注入 0、无穷等占位数值

### Requirement: 派生指标注入风险辩论与裁决上下文

激进/保守/中性三方风险辩论与 Risk Judge 的 LLM context SHALL 注入代码计算的派生指标行（格式如「派生指标（代码计算）：止损距离 8.1%、赔率 1.90:1」）；watch/hold 或指标为空时不注入。辩论与裁决 prompt SHALL 注明该行数值由代码计算。

#### Scenario: 辩论方使用同一组数

- **WHEN** 风险辩论 R1 轮构建各辩手 context
- **THEN** 三方 context SHALL 包含同一派生指标行（同值同源），辩论方 prompt 注明「算术已由代码完成，直接引用，MUST NOT 自行重算或改写」

#### Scenario: watch 方案不注入

- **WHEN** 决策 action 为 watch 或 hold
- **THEN** context SHALL NOT 出现派生指标行

### Requirement: LLM 自算数值不作为下游真值

当 reasoning 文本中的自算数值与代码计算值冲突时，下游（裁决 context、报告渲染、评估材料）SHALL 以代码计算值为准；代码计算值缺失时按缺失处理，MUST NOT 回退采用 LLM 自算值。

**原位修正（2026-09-19 处置；2026-09-21 扩展覆盖）**：trader 与 risk_judge（final_trade_decision 写入方）产出的 reasoning 文本 SHALL 经确定性自检——文本中与代码计算 `risk_reward_ratio` 冲突的赔率表述 SHALL 原位替换为代码计算值（保留原文其余内容，无 LLM 参与），替换 SHALL 记入 telemetry（`payout_ratio_corrected`）；代码计算值缺失（派生指标 None）时跳过修正、维持「按缺失处理」语义。相对容差 10% 以内的差异视为四舍五入，不修正。

赔率表述 SHALL 覆盖两种形态（证据：600030 终稿「赔率约1.78倍纸面占优」——risk_judge 修改止损后旧赔率残留，`N:1` 形态正则未命中）：

- `N:1` / `N：1` 型（如「赔率约1.7:1」）
- `N倍` / `N 倍` 型（如「赔率约1.78倍」）

**转述护栏**：赔率表述匹配数字后近距离（12 字符）出现批评语境词（`批评`、`质疑`、`反驳`、`驳回`）时，该处 SHALL NOT 原位替换——数字紧跟批评短语 = 转述辩论对方的赔率判断，替换可能反转原批评语义（如「赔率1.55:1不合格的批评」被替换后批评指向失真）；冲突 SHALL 仍计数上报（telemetry `payout_ratio_conflict_skipped`，逐处累加），供评审与批次归因消费。辩论主语词（激进方/保守方/中性方等）SHALL NOT 作为护栏词——出现在匹配数字之后是新句主语（600030「赔率约1.78倍纸面占优。激进方建议…」为自报+后续叙述，须替换），出现在数字之前不在扫描窗口内（窗口自赔率关键词起算）。

(Previously: 原位修正（2026-09-19 处置，证据：601899 终稿自称「赔率约1.7:1」而代码计算 1.24:1；000333 初稿自称「约2.6:1」而代码计算 2.00:1——两例横跨 Trader 与风控层，错数穿透全部下游原样渲染）：trader 与 risk_judge（final_trade_decision 写入方）产出的 reasoning 文本 SHALL 经确定性自检——文本中与代码计算 `risk_reward_ratio` 冲突的 `N:1` 型赔率表述 SHALL 原位替换为代码计算值（保留原文其余内容，无 LLM 参与），替换 SHALL 记入 telemetry（`payout_ratio_corrected`）；代码计算值缺失（派生指标 None）时跳过修正、维持「按缺失处理」语义。相对容差 10% 以内的差异视为四舍五入，不修正。)

#### Scenario: N倍 形态的旧赔率残留被替换

- **GIVEN** risk_judge 将止损从 25.42 改为 25.3（派生赔率随之 1.77 → 1.57）
- **WHEN** 终稿 reasoning 含「赔率约1.78倍纸面占优」
- **THEN** 该表述 SHALL 被原位替换为代码计算值（1.57）倍
- **AND** `payout_ratio_corrected` SHALL 为 True

#### Scenario: 冲突裁决

- **WHEN** reasoning 文本声称「赔率 2.5:1」而代码计算为 1.90:1
- **THEN** 注入辩论 context 与报告渲染的 SHALL 均为 1.90:1

#### Scenario: 文本赔率原位修正

- **WHEN** trader/risk_judge 产出的 reasoning 含「赔率约1.7:1」而同一决策的代码计算 risk_reward_ratio = 1.24
- **THEN** 该 reasoning 文本 SHALL 被修正为「赔率约1.24:1」（其余文字不动），修正 SHALL 记入 telemetry，SHALL NOT 触发 LLM 重写

#### Scenario: 容差内不修正

- **WHEN** reasoning 声称「赔率约1.9:1」而代码计算为 1.90:1（或相对差 <10%）
- **THEN** 文本 SHALL 保持原样，无 telemetry

#### Scenario: 转述辩论数字不替换但计数

- **GIVEN** 终稿派生赔率为 2.23
- **WHEN** reasoning 含「激进方对赔率1.55:1不合格的批评被部分采纳」
- **THEN** 该处 SHALL 保持原文不变
- **AND** `payout_ratio_conflict_skipped` SHALL 计 1

#### Scenario: 转述窗口外的自报冲突照常替换

- **GIVEN** 终稿派生赔率与文本自报冲突
- **WHEN** 冲突表述所在扫描窗口不含批评语境词
- **THEN** 按既有 `N:1` / `N倍` 替换语义执行

