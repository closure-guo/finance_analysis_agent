## ADDED Requirements

### Requirement: 非执行动作结构化理由契约

`TradeDecision` SHALL 支持 `inaction_reason`（string）与 `reeval_triggers`（string 列表）两个结构化字段，分别承载「不行动原因」与「可观察的再评估触发条件」。action 为 watch 或 hold（非执行动作）时 SHALL 申报两者；action 为 buy/sell 时两者无约束（价检语义不变）。输入清洗 SHALL 与既有先例一致：`reeval_triggers` 为 `None`/非列表时归一为 `[]`，单字符串归一为单元素列表，非字符串条目丢弃；`inaction_reason` 为纯空白等同缺失。清洗 MUST NOT 抛解析异常中断管线。

#### Scenario: 非执行动作缺理由打回一次后放行

- **WHEN** trader 产出的 plan 为 watch 或 hold，且 `inaction_reason` 或 `reeval_triggers` 缺失
- **THEN** 价位 sanity 校验节点 SHALL 判定理由检查 fail 并打回 trader 一次，feedback SHALL 列出缺失项并要求结构化申报
- **AND** 打回后仍缺失时 SHALL 放行前进 + 检查结果如实标注「已打回仍未申报」，MUST NOT 死循环

#### Scenario: 终稿非执行动作缺理由打回一次后放行

- **WHEN** risk_judge 终稿决策（`final_trade_decision`）为 watch 或 hold，且 `inaction_reason` 或 `reeval_triggers` 缺失
- **THEN** 终稿完整性检查 SHALL 打回 risk_judge 一次要求补全（与 `final_price_check` 同款一次重试语义）
- **AND** 仍缺失时 SHALL 放行 + 如实标注，不虚构内容

#### Scenario: 噪声形态清洗不炸管线

- **WHEN** LLM 输出的 `reeval_triggers` 为 `null`、单字符串、或含非字符串条目的混合列表
- **THEN** `null`/非列表 SHALL 归一为 `[]`；单字符串 SHALL 归一为单元素列表；非字符串条目 SHALL 被丢弃
- **AND** 校验 MUST NOT 因噪声形态抛 ValidationError 中断管线

#### Scenario: 执行动作不受理由约束

- **WHEN** action 为 buy 或 sell
- **THEN** 理由检查 SHALL 不要求 `inaction_reason`/`reeval_triggers`，价位必填校验语义 SHALL 保持不变
