# Proposal: update-sell-action-typing

## Why

回归评审 P1（issue #188）：sell 决策的执行框架概念混淆——**减仓**（持有者退出敞口）与**做空**（建立方向性空头）共用一套 entry/stop/target 模板。实证（10-02 上午拓荆报告）：「入场价 640 / 止损 700 / 目标 571」对持有者语义不通（「价格涨到 700 触及止损应立即离场」——涨了为什么离场？），risk 辩论 neutral 方当场点破但终稿未解决。根因：TradeDecision schema 单模板 + trader prompt 的 sell 语义混写（「强信念退出/减仓」）。

## What Changes

- **schema 渐进分型（非 BREAKING）**：TradeDecision 新增 `sell_type: Literal["exit", "short"] | None` 与 `exit_schedule: str | None`（减仓节奏自由文本，如「分两批：现价减半、跌破600清仓」）；action 枚举不变
  - `exit`（持有者减仓）：**豁免** entry/stop/target 必填（复用 watch/hold 的「无建仓参数」渲染语义——不渲染硬价格行，渲染「减仓节奏」行）；重新介入条件的天然载体为既有 `reeval_triggers`
  - `short`（做空建仓）：现有模板不变（entry/stop/target 必填 + 赔率/止损距离派生）
- **申报约束**：trader/risk_judge prompt 要求 sell 决策 MUST 申报 sell_type；risk_judge 校验 sell 缺 sell_type → 打回申报一次（复用既有打回模式），仍缺 → 默认 `short`（保守：维持现行价位模板语义）+ final_check 如实标注
- **渲染分模板**（report-decision-rendering MODIFIED）：exit 渲染减仓节奏行（缺失如实「未申报」）+ 不渲染入场/止损/目标价；short 走现行 buy/sell 参数行
- **结算层零改动**：outcome 的 `sell→short` 方向映射对 exit 结算数学一致（exit/short 均「价格下跌获益」，差异仅执行结构）；judgment.py 注释补充该语义声明
- prompts 变更须 `deploy_prompts.py` 同步发布（prompt-deploy-consistency）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `report-decision-rendering`: 「交易决策节渲染操作参数」MODIFIED——sell 按 sell_type 分模板渲染；「参数缺失时诚实标注」补充 exit_schedule 缺失标注
- `agent-prompt-contracts`: trader/risk_judge 输出契约新增 sell_type/exit_schedule 申报要求

## Impact

- `src/finance_agent/models.py`：TradeDecision 两字段 + 归一 validator（sell_type 大小写/同义词容错）
- `src/finance_agent/nodes/validate.py` + `nodes/risk.py`：`final_price_missing` 对 sell_type=exit 豁免三价位、要求 exit_schedule；sell 缺 sell_type 打回回路（risk_judge）
- `src/finance_agent/nodes/report.py`：`_format_trade_decision` 分模板
- `src/finance_agent/prompts/trader.md` + `risk_judge.md`：sell_type 申报要求与模板说明（deploy_prompts 同步）
- `src/finance_agent/outcome/track_record/judgment.py`：注释级语义声明（代码零改动）
- 测试：models 归一 / 校验豁免与打回 / 渲染分模板三组
- 范围外：滞回联动（add-decision-hysteresis 后续）、buy 侧对称分型（open/add，评审未提出、YAGNI）

**非交互类变更（后端决策语义 + 报告渲染）→ 不适用 E2E 门禁**
