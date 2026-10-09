# Proposal: add-event-delivery-hardening

## Why

`add-event-delivery-resilience`（PR #224）final whole-branch review 的 7 项遗留记账
（issue #227，均不阻塞合并、归档后跟进）。本变更实施其中 1-6 项；第 7 项
（watchdog 场景 A/D 理论 flake 窗口）issue 已裁决「实测稳定、CI 出现 flake 再治」，
不在本变更内。

核心动机：

1. `_drop_counts` 随进程驻留慢性泄漏（per-session 计数无清理）。
2. 消费端长期僵死时，非终态事件逐个等 30s 入队超时（~40 边界事件最坏 15-20 分钟
   收尾尾延迟）——需要连续 undeliverable 熔断降级。
3. spec「积压状态可查询」现仅靠丢弃节流日志勉强满足，队列深度不可查——挂运维出口。
4. 满队列下终态事件送达、重连「明细丢失+终态在」缺 incident 形状行为测试。

## What Changes

- **Drop 计数生命周期**：`StreamRegistry` 新增 `clear_drop_counts`；三条运行路径
  结束时清理（registry task `_notify_and_cleanup` / ReAct `_background_consume`
  finally / fast path `PipelineRunner._run` finally），终结慢性泄漏。
- **熔断降级**（行为变更）：连续 N 次（默认 3）undeliverable 后，非终态事件降级为
  丢弃+计数（`breaker_degraded` 桶），不再逐个 30s 有界等待；终态哨兵（None）
  MUST 保留有界等待路径不被熔断丢弃；任一事件成功入队重置连续计数。
- **积压运维出口**：`backlog_stats` 增补订阅者队列深度；新增 `all_backlog_stats`
  与 `GET /api/v1/ops/stream-backlog`（spec「积压状态可查询」的实现补全）。
- **可测试性重构**：`_put_event` 闭包逻辑抽为模块级 `BoundedEventSink`
  （timeout/threshold 可注入），满队列终态送达与熔断行为可单测。
- **incident 形状专测**：重连「明细丢失+终态在」行为测试。

## Capabilities

- **Modified Capabilities**:
  - `session-streaming`（MODIFIED：发布积压可观测与背压——增补熔断降级语义与
    运维查询出口；既有分级处置与终态不丢弃约束保持不变）

## Impact

- `src/finance_agent/stream_registry.py`（清理 + 队列深度 + 全会话快照）
- `src/finance_agent/agent_factory.py`（BoundedEventSink 抽取 + 熔断）
- `src/finance_agent/pipeline_runner.py`（fast path 结束清理 drop 计数）
- `src/finance_agent/ops_api.py`（stream-backlog 只读端点）
- 测试：`tests/test_stream_registry.py`、`tests/test_stream_registry_terminal_priority.py`、
  `tests/test_bounded_event_sink.py`（新）
- 纯后端事件链路；健康消费者路径行为零变化（熔断仅在连续投递失败后触发）。
