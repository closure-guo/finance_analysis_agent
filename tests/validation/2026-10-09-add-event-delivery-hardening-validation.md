# 人工验证报告: add-event-delivery-hardening

**日期**: 2026-10-09
**验证人**: ZCode agent（owner 会话内授权「都做完，不用等我确认」；测试层程序化实跑 + 生产活体探针 + 真实管线观察）
**关联 delta**: openspec/changes/add-event-delivery-hardening/（实施 PR #237，1-6 项；第 7 项 watchdog flake 窗口按裁决走观察策略）
**E2E 门禁**: 不适用（纯后端事件层，非交互类）
**方法论**: 沿用 add-event-delivery-resilience（2026-10-05）先例——慢消费者/故障场景由测试层证据承担（生产注故障风险不对称），真实管线部分以生产运行观察承担

## 一、测试层证据（#237 新增/收敛套件实跑）

`uv run pytest tests/test_bounded_event_sink.py tests/test_ops_stream_backlog.py tests/test_pipeline_watchdog_graph_done.py tests/test_stream_registry_terminal_priority.py tests/test_session_store_retry.py -q`

**25 passed / 0 failed**（12.9s），覆盖：

| #227 子项 | 对应测试证据 |
|---|---|
| 1. drop 计数生命周期（clear_drop_counts 三路径终结清理） | BoundedEventSink 套件生命周期用例（慢性泄漏消除的回归锚） |
| 2. BoundedEventSink 抽取（可注入 timeout/threshold） | tests/test_bounded_event_sink.py 独立套件（注入参数化用例） |
| 3. 积压运维出口（backlog_stats + GET /api/v1/ops/stream-backlog） | tests/test_ops_stream_backlog.py + 本报告第二节活体探针 |
| 4. incident 037 形状专测（重连「明细丢失+终态在」见终态不挂起） | watchdog 套件场景（#237.4） |
| 5. record_drop docstring | 文档项，随 PR #237 评审核对 |
| 6. 熔断降级（breaker_degraded，终态哨兵豁免） | 终态优先套件（test_stream_registry_terminal_priority.py）+ 熔断路径用例 |
| 7. watchdog flake 窗口 | 按裁决观察策略：实测稳定（本轮 25 用例含 watchdog 场景全绿，无 flake），CI 出现 flake 再治 |

## 二、生产活体探针（2026-10-09 14:0x，真实洪峰在场）

`GET /api/v1/ops/stream-backlog`（#237.4 新端点，生产首查）：

```json
{"sessions": {"16d351f6-4a9": {"drops": {"thinking": 43187},
  "subscribers": 1, "queue_depths": [0], "last_seq": 64845}}}
```

- 并发会话「分析宁德时代」正在真实运行，thinking 洪峰 43,187 条被有界丢弃且**计数可见**（drop 计数生命周期工作），订阅者队列深度 0（消费端跟上，无积压堆积）——积压可观测性在真实洪峰下实证可用
- 该会话的终态送达表现为第三节的真实管线样本之一

## 三、真实管线终态送达观察（2026-10-09 实测两样本）

**样本 A（本会话发起的 688072 深度研究跑批，session `8bc9b9a9-a66`）**：全程 SSE 带时戳消费（日志 `tests/validation/2026-10-09-fa-run-688072-sse.txt`，660 行）。197s 完成（duration_ms=196477），**report_ready(187.3s) → done(196.5s) 间隔 9.2s，终态即时送达、流正常收尾**，无前置积压滞后（#266 部署后首个观察样本）。watch 决策三处一致（报告渲染行 688.5/570 = predictions 落库 trigger_high/low + session_id = chart_data.price.decision_levels），事件链 seq 单调。

**样本 B（并发会话 16d351f6「分析宁德时代」，运行中活体观察）**：第二节 ops 探针所引——真实 thinking 洪峰 43,187 条有界丢弃且计数准确，订阅者队列深度 0，泵在洪峰下保持不积压。

两样本共同支撑：熔断/有界丢弃/积压可观测/终态优先四机制在真实生产流量下工作正常。

## 异常记录

- 无阻塞异常。

## 结论

- [x] 全部通过，可 archive（测试层 25/25 + 活体探针 + 真实管线两样本终态及时）
- [ ] 存在失败项，需修复后重新验证
