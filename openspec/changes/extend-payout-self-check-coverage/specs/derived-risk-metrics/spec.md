# Delta for derived-risk-metrics

## MODIFIED Requirements

### Requirement: LLM 自算数值不作为下游真值

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

#### Scenario: 转述辩论数字不替换但计数

- **GIVEN** 终稿派生赔率为 2.23
- **WHEN** reasoning 含「激进方对赔率1.55:1不合格的批评被部分采纳」
- **THEN** 该处 SHALL 保持原文不变
- **AND** `payout_ratio_conflict_skipped` SHALL 计 1

#### Scenario: 转述窗口外的自报冲突照常替换

- **GIVEN** 终稿派生赔率与文本自报冲突
- **WHEN** 冲突表述所在扫描窗口不含辩论指涉词
- **THEN** 按既有 `N:1` / `N倍` 替换语义执行
