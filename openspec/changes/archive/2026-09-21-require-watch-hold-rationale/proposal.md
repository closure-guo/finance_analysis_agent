## Why

决策层「全 watch」取证（2026-09-21，`docs/evals/2026-09-21-决策层全watch取证.md`）确认：生产流量 89% 为非执行动作（watch 63% / hold 26%），成因是 Trader 默认姿态。非执行动作当前只要求自由文本 `reasoning`——报告里「再评估触发条件」只渲染占位行「见理由」（report-decision-rendering spec 明言「当前决策 JSON 无结构化触发字段，不得凭空编造」），B5 可执行性 rubric（`evals/causal_ablation/family_b_judge.py:227`「'观望等待好转' = 差」）已在按「明确的再评估触发条件」评分但管线不保证产出。owner 选定取证选项 b：非执行动作强制结构化申报「不行动原因 + 再评估触发条件」——不改动作分布，提升信息量、可回测性与 judge 可评性。

## What Changes

- **TradeDecision schema 扩展**：新增 `inaction_reason`（不行动原因，具体到当前不满足执行条件的点）+ `reeval_triggers: list[str]`（可观察的再评估触发条件）；非执行动作（watch/hold）MUST 申报两者；LLM 噪声清洗沿用 evidence_refs 先例（None/非列表 → []，非 str 条目丢弃不字符串化）。
- **交易员侧强制回路**：`validate_trade_prices` 节点增加非执行动作理由完整性检查——watch/hold 首次缺失打回 trader 一次（feedback 列出缺失项），仍缺失放行 + 如实标注（同价位必填语义，避免死循环）。
- **终稿侧强制回路**：`risk_judge` 终稿完整性检查（`final_price_check` 同款回路）扩展到非执行动作理由——终稿为 watch/hold 且缺理由时打回一次，仍缺如实标注。
- **prompt 契约**：`trader.md` 输出要求 + JSON 示例补非执行动作形态；`risk_judge.md` 继承要求（可改写内容，不得置空）；prompt 变更走 `deploy_prompts` 发布纪律（eval 门禁依赖）。
- **报告渲染**：watch/hold 决策节的「再评估触发条件: 见理由」占位替换为结构化渲染（有字段渲染编号条目；字段缺失时如实标注「未申报」，MUST NOT 编造）；新增「不行动原因」行。
- **state 声明**：新增检查键须过「节点产出键 ⊆ AnalysisState 声明与图通道」门禁。
- **下游受益（非目标，自动获得）**：judge 材料序列化（`evals/extract.py::_serialize_decision`）自动携带新字段，B5 可执行性维度与 consistency 可评。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `agent-node-contracts`：新增 requirement「非执行动作结构化理由契约」——TradeDecision 字段与噪声清洗、非执行动作必填判定、两侧（Trader 打回 / 终稿打回）一次重试语义、state 检查键声明。
- `report-decision-rendering`：「watch/hold 决策不渲染硬价格」scenario 的「注明再评估触发条件位于理由文本中（当前决策 JSON 无结构化触发字段，不得凭空编造结构化条目）」MODIFIED 为结构化渲染 + 缺失诚实标注。

## Impact

- `src/finance_agent/models.py`：TradeDecision 新增字段 + 清洗校验
- `src/finance_agent/nodes/validate.py`：非执行动作理由检查（trader 侧回路）
- `src/finance_agent/nodes/risk.py`：终稿理由完整性检查（同 `final_price_check` 回路）
- `src/finance_agent/nodes/trader.py`：消费打回反馈（同 `price_check_feedback` 通道）
- `src/finance_agent/nodes/report.py`：`_format_trade_decision` watch/hold 分支
- `src/finance_agent/state.py`：检查键声明
- `src/finance_agent/prompts/trader.md`、`risk_judge.md`（deploy_prompts 发布）
- stub 契约：`_STUB_TRADE_DECISION`（hold 形态）需带字段，`test_stub_contract_sync` 护栏强制同步
- 测试：models / validate / risk_judge / report / stub 契约
- 不动：动作分布（本变更不改 watch 主导）、价检语义、图结构（节点名与边不变）
