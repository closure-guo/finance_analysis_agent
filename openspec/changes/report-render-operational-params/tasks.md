# Tasks: report-render-operational-params

## 1. 前置确认

- [x] 1.1 确认 `harden-decision-report-semantics` 已归档（`openspec/changes/archive/` 可见）；未归档则本组以下任务挂起，仅允许进行纯规范类任务

## 2. 测试先行

- [x] 2.1 报告渲染测试新增用例：buy 决策（全参数有效）渲染方向/置信度/仓位/入场/止损/目标/理由七要素，价位与 JSON 原值一致
- [x] 2.2 测试用例：watch 决策不渲染入场/止损/目标价行，渲染「触发条件见理由」指引，仓位档位正常渲染
- [x] 2.3 测试用例：sell 决策 stop_loss/target_price 为 0 时渲染「未提供」，不静默跳过行、不影响其他参数渲染（比亚迪形态回归）
- [x] 2.4 测试用例：`price_level_corrected=True` 时价位修正行保留且置于参数行之后

## 3. 实现

- [x] 3.1 `_format_trade_decision` 增加 `_fmt_price` 工具（`value and value > 0` 判有效，否则「未提供」），按 action 分支渲染参数行
- [x] 3.2 watch/hold 分支渲染触发条件指引行（注明见 reasoning，不结构化）
- [x] 3.3 dict 形态输入（`trader_plan` 回退路径）同样支持参数渲染，键缺失按「未提供」处理
- [x] 3.4 派生指标（赔率、止损距离%）由代码按参数原值计算渲染，不取 reasoning 中心算值；测试：reasoning 自算错误时报告仍渲染正确代码值

## 4. 验证与收口

- [x] 4.1 `uv run pytest` 全量绿 + `uv run ruff check` + `uv run mypy`
- [x] 4.2 生成一份真实分析报告（buy 与 watch 各一），人工核对决策节版式与参数数值（交互类变更人工验证环节）——600036/600519 watch + 601318 buy(未提供形态) 三次真实运行
- [x] 4.3 人工验证报告落 `tests/validation/`（报告渲染截图 + 参数核对记录）——tests/validation/delta-e2e-验证记录.md
- [ ] 4.4 tasks 全勾后走 `openspec archive`，spec sync 合入主规范 `openspec/specs/report-decision-rendering/`
