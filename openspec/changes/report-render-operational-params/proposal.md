# Proposal: report-render-operational-params

## Why

报告的「交易决策」节目前只渲染方向（watch/buy/hold/sell）、置信度、理由三样，而 `TradeDecision` 上的 `position_size`/`entry_price`/`stop_loss`/`target_price` 被渲染层丢弃。这些参数在管线里全程存在且被下游消费：trader.md 强制要求输出、`validate_trade_prices` 校验价位、决策落库后日批结算按止损/目标/超期规则执行。结果是用户看到的报告与系统实际执行的决策参数不一致；风险辩论中保守方甚至以「止损/目标价缺失是风控半成品、不可交付」批评方案——管线内部已把完整操作参数当作质量标准，最终交付物反而没跟上。

## What Changes

- `report.py` 的 `_format_trade_decision` 渲染补齐操作参数：
  - 所有 action：新增**仓位档位**行（light/moderate/heavy）；
  - buy/sell：新增**入场价 / 止损价 / 目标价**行；价格为 0 或缺失时如实标注「未提供」（不编造、不静默跳过）；
  - watch/hold：不渲染硬价格（语义上无建仓参数），改为渲染**再评估触发条件**占位——决策 JSON 无结构化触发字段，触发条件目前只存在于 `reasoning` 自由文本中，渲染层注明「触发条件见理由」，不凭空结构化；
  - 保留既有「价位修正」标注（toolize-price-levels 可观测语义不变）。
- 前端报告视图与导出（Word/PPT/PDF）自动继承 Markdown 渲染结果，无需单独改动。

## Capabilities

### New Capabilities

- `report-decision-rendering`: 报告「交易决策」节的渲染契约——必含字段（方向/置信度/仓位档位/理由）、按 action 区分的参数渲染规则（buy/sell 含入场/止损/目标价，watch/hold 含触发条件指引）、缺失值的诚实标注规则。

### Modified Capabilities

（无——现有主规范没有覆盖报告交易决策节渲染的条目；`harden-decision-report-semantics` delta 触及的是 agent-evaluation-suite/agent-node-contracts 等 judge 与节点契约区域，与本能力无规范冲突，仅在实现文件 `report.py` 上有时间顺序依赖。）

## Impact

- **代码**：`src/finance_agent/nodes/report.py`（`_format_trade_decision` 及可能的 `_format_debate_message` 相邻渲染函数）；无 API/依赖变更。
- **测试**：`tests/` 报告渲染测试补字段断言（含 0 值/缺失的诚实标注路径）。
- **依赖顺序**：实现排在 `harden-decision-report-semantics` 归档之后（同文件相邻区域，避免合并冲突与语义误读）；规范本身无冲突，可先归档本 delta 的规范工件。
- **关联**：决策落库（decision-outcome）与日批结算不受影响——它们消费的是原始 JSON，不是报告渲染。
