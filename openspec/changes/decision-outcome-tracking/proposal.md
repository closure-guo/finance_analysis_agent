## Why

`TradeDecision`（`models.py:55-68`：action + confidence + position_size + entry_price + stop_loss + target_price）产出后即被遗忘，系统在"产出决策"那一刻断了反馈环。全仓 grep `decision_log / pnl / actual_return / forward_return / post_decision` 零命中 —— 没有任何表存储决策历史、没有定时任务拉行情核对、没有任何决策效果 Score。后果：prompt 改了不知好坏、模型升级无法验证、所有调优凭手感；一个产交易决策的 Agent 对"建议赚没赚钱"完全失明。这是交易 Agent 最致命的评估盲区，且与 delta `agent-evaluation-suite` 互补：后者评"产出质量"（论据通不通），本 delta 评"事后效果"（决策对不对）。

## What Changes

1. **新建 `decision-outcome` capability** —— 定义决策落库、事后追踪、效果 Score、A 股异常处理、基准对比五类行为契约。
2. **决策落库** —— `TradeDecision` 产出时同步落 `decision_log` 表（action / entry_price / stop_loss / target_price / timestamp / ticker / langfuse_trace_id / status=open），复用现有 SQLite（与 session_store 同库）。
3. **事后行情追踪** —— 日批定时任务（每日收盘后）拉收盘价，更新 open 决策：触及止损 → `hit_stop`、触及目标 → `hit_target`、超持仓周期 → `expired`，记录实际结算价与持有期收益。
4. **决策效果 Score 反向上报** —— 结算后向 Langfuse 上报 `decision_hit`（方向是否正确，BOOLEAN）、`decision_return`（实际收益率，NUMERIC）、`decision_excess`（相对基准超额，NUMERIC），关联原 `langfuse_trace_id`，使"决策 → trace → 效果"闭环可追溯。
5. **A 股异常结算规则** —— 涨跌停（止损触及但一字板未成交）、停牌（持仓期顺延）、`sell` 方向（forward return 取负，即 sell 后跌为正收益）、`hold/watch`（不产生交易，按方向对称评估）的统一结算语义。
6. **基准对比** —— 首版基准沪深 300（000300）同期收益率，`decision_excess = decision_return - benchmark_return`。

## Capabilities

### New Capabilities

- `decision-outcome`: 交易决策的事后效果闭环 —— 决策落库 + 行情追踪 + 效果 Score + A 股异常结算 + 基准对比，补齐"决策对不对"的反馈环。

### Modified Capabilities

无。`TradeDecision` 模型（`models.py`）字段不变，本 delta 只新增旁路落库与事后追踪，不改业务管线行为；`session-persistence` 的 session_store 表不动，`decision_log` 为独立新表。

## Impact

- **新增代码**：`decision_log` 表（SQLite migration）、`decision_outcome/` 模块（结算器 + 定时任务 + 行情拉取 + Score 上报）、配置项（持仓周期 / 基准代码 / 结算时间）。
- **依赖**：复用 AKShare 日 K 拉取（`fetch.py` 已有 K 线逻辑），不引入新数据源；复用 `langfuse_tracing.get_langfuse()` 的 `score(trace_id=...)` 反向上报。
- **协调**：与 `agent-evaluation-suite` 互补（产出质量 vs 事后效果，两者 Score 互不冲突，可同 trace 共存）；与 `agent-trace-content-fidelity` 无直接依赖（本 delta 只需 trace_id 关联，不依赖 span 内容）。
- **架构决策**：涉及新表 + 定时任务框架 + 反向后置 Score，**建议人工落一条 ADR**（agent 不得新建 ADR）；本 delta 的 design 给出选型建议待人工确认。
- **风险**：中高 —— A 股结算规则复杂（涨跌停 / 停牌 / 复权），首版用保守近似；定时任务是新增运行组件，需考虑失败重试与幂等；反向上报 Score 依赖 Langfuse trace 长期可查（trace 保留策略需确认）。
