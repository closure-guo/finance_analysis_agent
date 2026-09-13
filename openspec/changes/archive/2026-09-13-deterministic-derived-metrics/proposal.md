# Proposal: deterministic-derived-metrics

## Why

交易方案的关键派生数字（止损距离、风险收益比）目前由 LLM 在 reasoning 里心算，无任何校验：citation 门禁只核对「对上游数据的引用」，决策内部自算术不在任何数据源里，judge 与人工抽查默认都不覆盖。2025 年行业共识（PAL/PoT 一线工作与临床/金融确定性计算实践）是高风险数字场景 SHALL 由确定性代码计算、LLM 只负责引用与解读。本管线每轮派生运算仅两三个且全部可枚举，适用最严格的形态：代码直接算，LLM 零参与。

## What Changes

- `validate_trade_prices`（纯规则节点，已是价位把关位置）在 pass/corrected 时**顺带计算**派生指标：止损距离百分比 `(entry-stop)/entry`、风险收益比 `(target-entry)/(entry-stop)`，写入 state（如 `derived_metrics`），不做 LLM 调用。
- 风险辩论三方与 Risk Judge 的 LLM context 注入一行「代码计算的派生指标」（止损距离 X%、赔率 Y:1），辩论方与裁决直接采用同一组数，MUST NOT 自行重算或改写；prompt 同步补充一句来源说明（算术由代码负责，辩论专注判断）。
- watch/hold 决策不计算（无止损/目标语义），派生指标为空且 context 不注入。
- 报告侧消费同一 state 值（渲染契约见 `report-render-operational-params` delta，此处不重复定义）。

## Capabilities

### New Capabilities

- `derived-risk-metrics`: 派生风险指标的确定性计算契约——计算公式与触发条件（buy/sell 且价位有效）、state 落点、辩论/裁决 context 注入格式、LLM 禁止自行重算的行为约束、watch/hold 与参数缺失时的空值语义。

### Modified Capabilities

（无——`agent-node-contracts`/`agent-prompt-contracts` 正被待归档的 `harden-decision-report-semantics` delta 触及，为避免规范冲突，本 delta 以新能力承载；实现排期上同样排在其归档之后。）

## Impact

- **代码**：`src/finance_agent/nodes/validate.py`（计算落 state）、`src/finance_agent/nodes/risk.py`（辩论/裁决 context 注入）、`src/finance_agent/prompts/`（风险辩论与 risk_judge prompt 各补一句来源说明）；无 API/依赖变更。
- **Prompt 发布**：prompt 修改后 MUST 执行 `uv run python scripts/deploy_prompts.py`，否则 eval 门禁拒绝运行。
- **关联**：报告渲染契约在 `report-render-operational-params`；本 delta 只管「算」与「喂回」，不管「展示」。
