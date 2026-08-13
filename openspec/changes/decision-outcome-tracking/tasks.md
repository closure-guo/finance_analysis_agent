# Tasks: decision-outcome-tracking

> 粗粒度验收 checklist。细粒度 TDD 步骤由 Step 2 writing-plans 产出至 `docs/superpowers/plans/`，不在此处。

## 前置

- [ ] 人工 ADR 落地：定时任务框架选型（建议 APScheduler in-process）、`decision_log` 表归属、基准与持仓周期默认值（agent 不自建 ADR）

## 验收项

- [ ] `decision_log` 表建立（SQLite migration），TradeDecision 产出即落库，`status=open`，含 `langfuse_trace_id`
- [ ] 落库旁路不阻断业务（SQLite 写失败时管线仍正常完成，仅日志）
- [ ] 日批定时任务（收盘后）结算 open 决策：`hit_stop`/`hit_target`/`expired`，止损优先于目标，超期强制结算
- [ ] 任务幂等（已 settled 跳过）+ 失败重试 + `data_stale` 告警（连续无数据）
- [ ] 方向符号化：buy 正向、sell/hold/watch 取负；`decision_hit = return > 0`
- [ ] A 股异常结算：一字板递延至可成交价、停牌不计入持仓期且周期顺延、前复权日 K
- [ ] 基准对比：沪深 300（000300）同期收益，`decision_excess = return - benchmark`；`BENCHMARK_CODE`/`MAX_HOLD_DAYS` 可配
- [ ] 结算后反向上报 3 个 Score（`decision_hit`/`decision_return`/`decision_excess`）到 Langfuse，关联原 trace_id；trace 不可查时记 WARN 不阻断
- [ ] 结算逻辑全部纯函数 + 历史 fixture 测试（不依赖 LLM、不调真实行情即时性）
- [ ] `uv run pytest` 全过、`uv run ruff check` 无错误、`uv run mypy` 无错误
- [ ] `openspec validate decision-outcome-tracking --strict` 通过
- [ ] 人工验证报告落 `tests/validation/`（5-10 只历史票 mock 决策对照实际走势验证结算正确）
