# Design: deterministic-derived-metrics

## Context

管线现状：trader 输出价位 → `validate_trade_prices`（`nodes/validate.py`，纯规则校验，fail 打回 / corrected 修正 / pass 放行）→ 风险辩论（`nodes/risk.py` 构建三方 context）→ Risk Judge。派生数字（止损距离、赔率）目前只存在于 reasoning 自由文本中，由 LLM 心算产出，无校验、无统一来源。

## Goals / Non-Goals

**Goals:**

- 派生指标单一真源：validate 节点计算一次，辩论、裁决、报告（经 `report-render-operational-params` 渲染契约）全部消费同一 state 值
- 零 LLM 参与：计算是四则运算，纯规则代码
- 辩论方不再各自心算赔率：心算值散落在各方 reasoning 里无法汇总核对（如平安案例中「名义1.9:1」「概率加权后向2:1倾斜」等多个口径并存），统一为代码单源后可被报告与评估直接引用

**Non-Goals:**

- 不做通用算式解释器（PAL/PoT 式 calc DSL）——可枚举指标用确定性代码即可，等真实错误案例出现再评估
- 不给 TradeDecision 新增字段（派生值落独立 state 键，决策 JSON 保持 trader 申报原值，二者职责分离）
- 不动 evals/extract 的 judge 变量格式（judge 材料如何呈现派生指标另行评估，避免与本 delta 及校准中 round 相互干扰）

## Decisions

1. **计算点选 validate_trade_prices 而非 trader 节点内**：validate 是纯规则节点且已持有校验通过的价位（corrected 时用修正后值），在此计算保证「进 state 的必是过审价位」；打回（fail）路径自然不计算。
2. **state 落独立键**（如 `derived_metrics`），不回写决策对象：决策 JSON 是 trader/Risk Judge 的申报原值（落库结算消费它），派生值是代码计算事实——混写会让「申报」与「实测」失去边界。
3. **注入格式一行人读文本**，不做结构化注入：辩论 context 已有预算治理，一行文本成本可忽略；结构化字段属 prompt 契约变更（agent-node-contracts 区域正被 harden delta 占用），避免冲突。
4. **prompt 改动最小化**：风险辩论与 risk_judge prompt 各补一句「派生指标由代码计算，直接引用」；修改后 MUST 执行 `scripts/deploy_prompts.py` 发布。

## Risks / Trade-offs

- **corrected 价位的两套数**：价位被参考带修正后，reasoning 里 LLM 自述的旧赔率与代码新算值并存——spec 已定「代码值为准」，报告渲染同样以代码值覆盖，用户看到的与结算的一致。
- **辩论 prompt 长度**：注入一行 ~40 字节，预算治理（llm-budget-governance）不受影响。
- **round 校准窗口**：本 delta 改变 risk 辩论 context 内容，属 judge 输入变化——实现排期在 harden 归档之后，且与 round8 材料版本（Trader 方案节等改动）合并考虑，避免一轮实验引入两个变量。
