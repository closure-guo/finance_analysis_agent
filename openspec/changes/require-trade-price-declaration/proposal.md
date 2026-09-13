## Why

连续 4 轮真实运行（round8 E2E 3/3 + round9 宁德 buy）中 trader 从不申报数值价位（entry/stop/target 全 null），根因是 validate.py 对 buy/sell 价位缺失**静默 pass**（「schema 可选，跳过校验」），trader 无任何反馈压力。后果：① 报告操作参数只能渲染「未提供」，用户拿不到可执行的入场/止损/目标；② derived_metrics（止损距离/赔率）在真实数据上从未生效——派生指标喂回风险辩论的机制空转；③ price_check fail→打回回路（incident 027 修复后激活）从未在真实数据触发。

## What Changes

- **validate 价位校验收紧**：buy/sell 决策的 entry/stop/target 任一缺失（None/0/负数）不再静默 pass，改为 price_check **fail 打回一次**（复用现有 attempts 回路），feedback 明确列出缺失项并要求申报数值价位；已打回一次仍缺失 → 放行（pass+note「已打回仍未申报」），报告端「未提供」兜底不变，避免死循环。
- **prompt 契约**：trader.md 增加「buy/sell MUST 申报数值价位」输出要求（watch/hold 豁免不变）；risk_judge.md 增加继承价位要求（可调整数值，不得置 null）。
- **预期效果**：buy/sell 决策带真实价位后，derived_metrics 真实数据路径激活（止损距离/赔率进风险辩论）、report-render-operational-params 的 buy+真实价位渲染形态可核。
- prompt 变更走 deploy_prompts 发布纪律（eval 门禁依赖）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `price-level-tooling`: 「交易价位 sanity 校验」要求更新——buy/sell 价位缺失从「跳过校验 pass」改为「fail 打回一次，仍缺失放行+如实标注」；新增「价位申报必填」scenario。

## Impact

- `src/finance_agent/nodes/validate.py`：价位缺失分支改 fail 逻辑（纯规则，无 LLM）。
- `src/finance_agent/prompts/trader.md`、`risk_judge.md`：输出契约行新增，deploy_prompts 发布。
- `tests/nodes/test_validate_trade_prices.py`：新增 TestPriceDeclarationRequired。
- 不改 TradeDecision schema（字段仍可选——打回放行路径需要 schema 保持宽松，prompt 契约承担必填约束）。
- 真实运行验证依赖 docker/Langfuse 可用（当前停机，实施后补跑）。
