# user-intent-propagation Specification

## Purpose

将用户研究聚焦（focus）贯穿多 Agent 管线：聚焦缺失时兜底生成，并向辩论层与风险层注入，保证各 Agent 的论证围绕用户真实关注展开。

## Requirements

### Requirement: focus 兜底提取

深度分析入口在意图澄清未收集到 focus（`req.focus` 为空）时，SHALL 对原始 query 执行关注点标签提取（与 `parse_focus_tags` 共享词表），并将命中标签合成为弱 focus 文本写入 `state["focus"]`；零命中时 SHALL 不注入（保持 focus 为空），MUST NOT 将原始 query 全文注入分析师层。

#### Scenario: 通用问法命中标签合成弱 focus

- **WHEN** 用户以「分析贵州茅台当前适不适合作为长期持有股买入？」发起深度分析且未填写 focus
- **THEN** 入口 SHALL 从 query 提取出含「中长期/持有」（mid_long_term）与「风险」或「买入」相关标签的弱 focus
- **AND** 该弱 focus SHALL 以「用户关注点: …」形式进入各层 context（与既有 focus_hint 行为一致）

#### Scenario: 零命中不硬造关注点

- **WHEN** query 不含任何词表关键词（如「帮我看看这只股票」）
- **THEN** focus SHALL 保持为空
- **AND** 各层 context SHALL NOT 出现合成的关注点行

#### Scenario: 原始 query 不进入分析师层

- **WHEN** focus 兜底触发
- **THEN** 分析师 context 中 SHALL 只出现合成后的弱 focus 行
- **AND** SHALL NOT 出现原始 query 全文

### Requirement: 辩论层与风险层 focus 注入

Bull/Bear 辩论与风险辩论（三方辩论及 Risk Judge）的 LLM context SHALL 包含 `focus_hint(state)` 注入行（与分析师/Trader/FM 同款）；focus 为空时 SHALL 不注入。

#### Scenario: 辩论 context 含用户关注点

- **WHEN** focus 非空且构建 Bull/Bear 辩论 context
- **THEN** context 中 SHALL 包含「用户关注点: <focus>」行

#### Scenario: 风险层 context 含用户关注点

- **WHEN** focus 非空且构建风险辩论三方或 Risk Judge 的 context
- **THEN** context 中 SHALL 包含「用户关注点: <focus>」行

#### Scenario: focus 为空时零注入

- **WHEN** focus 为空
- **THEN** 辩论层与风险层 context SHALL 与现行行为一致（无关注点行，零回归）
