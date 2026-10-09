# Delta for agent-prompt-contracts

## MODIFIED Requirements

### Requirement: 论据期次新鲜度

bear 辩论提示词与研究聚焦摘要生成器 MUST 携带论据期次新鲜度约束：引用财务数据的论据 SHALL 使用最新披露报告期口径；当负面趋势被最新报告期反转时（如年报口径连续下滑而最新中报回升），提示词 MUST 要求并列呈现反转事实（如「年报连续三年下滑，但最新中报已回升至 X%」），MUST NOT 仅引用历史期次单边表述而省略最新期次状态。全部分析师提示词 MUST 携带期次标注纪律：同一数值在年报/中报/单季等多个期次并存时（如 Q1 单季毛利率恰等于上年年报毛利率），正文引用 SHALL 显式标注期次（如「2024 年报毛利率 41.69%」「2026Q1 单季毛利率 41.69%」），MUST NOT 裸引数值或使用与所引期次不符的期次标注。
(Previously: 仅 bear 辩论提示词与研究聚焦摘要生成器携带期次新鲜度约束，无期次标注纪律。)

#### Scenario: bear prompt 携带新鲜度约束

- **WHEN** 加载 bear_debater 提示词
- **THEN** 模板中包含「负面论据使用最新披露期口径」与「趋势被最新期反转时并列呈现」的要求描述

#### Scenario: 摘要生成器携带期次并列约束

- **WHEN** 研究聚焦摘要生成（_build_focus_summary system 文案）
- **THEN** 文案 SHALL 包含「引用财务数据使用最新期次」与「最新期次与历史趋势方向相反时并列呈现、不得单边省略」的要求

#### Scenario: 分析师 prompt 携带期次标注纪律

- **WHEN** 加载任一分析师提示词（fundamental/technical/macro/sentiment_analyst）
- **THEN** 模板中包含「同一数值多期次并存时必须显式标注期次、不得裸引」的要求描述
