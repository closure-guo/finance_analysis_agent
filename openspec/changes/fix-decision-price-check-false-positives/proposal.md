# Proposal: fix-decision-price-check-false-positives

## Why

2026-10-02 拓荆科技(688072) 重跑被 update-decision-price-gate 门禁阻断，systematic-debugging 四相取证（Langfuse trace 7f43b9c9… + 纯函数确定性复现）裁决：**阻断源于校验器两个误报缺陷，非 LLM 不确定性**。更重要的反转：回归评审定性的原始 P0 案例（「LLM 输出 95 元幻觉价位」）实为缺陷 A 的误报——LLM 从未输出过 95 元价位，那是 reasoning 里「VaR95单日6.6%」的 95 被当成了股价。门禁已上线，误报即误拦：不修则含 VaR/复合触发条件的正常决策会被持续阻断。

## What Changes

- **缺陷 A——VaR 语境误报**：`_NON_PRICE_KEYWORDS` 增加 `var` 与 `在险价值`，风险度量语境的数值（VaR95 / VaR(95% / 在险价值95）不再进入价位校验
- **缺陷 B——复合触发条件误判空洞**：
  - `_BREAKDOWN_WORDS` 增加「回撤至」「回调至」（A 股回踩语境标准用词，与既有「回落至」同族）；
  - 复合条件豁免：同一触发条目内同一数值同时出现下破语境与上破语境（「先跌破/回撤至 X，再站稳 X」的回踩确认结构）时，该数值 SHALL NOT 判 empty_trigger——两个子条件串联，整体是前瞻有效门槛
- **回归固化**：688072 真实案例文本（gen1/gen2 触发条目 + VaR95 reasoning）进单元测试，断言修复后零 anomaly；spec 既有 7 场景行为不变
- **incident 034**：记录证据链与对评审原始诊断的更正（「95 元幻觉」实为校验器误报），更新 incidents README 索引

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `price-level-tooling`: 「决策文本价位与已验证技术指标交叉校验」的两条判定规则收窄——①归属匹配增加 VaR/在险价值非价格语境；②空洞形态增加复合条件豁免（同数值 down+up 共存不判空洞）

## Impact

- `src/finance_agent/metrics/decision_price_check.py`：词表两处 + `_check_snippet` 复合豁免逻辑（模块保持纯函数、不改判定阈值 2%）
- `tests/metrics/test_decision_price_check.py`：新增 688072 案例回归组
- `docs/incidents/034-decision-price-check-false-positives-20261002.md` + `docs/incidents/README.md`（索引）
- 范围外（本 delta 不动）：门禁自动阻断策略（owner 终裁挂起）、prompt 侧触发条件写法强化

**非交互类变更**（纯后端校验规则）→ 不适用 E2E 门禁与人工验证环节
