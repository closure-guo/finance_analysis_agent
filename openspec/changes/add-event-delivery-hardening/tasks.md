# Tasks: add-event-delivery-hardening

- [x] drop 计数生命周期：`clear_drop_counts` + 三路径结束清理（registry task /
      ReAct finally / fast path finally），慢性泄漏消除（TDD）
- [x] `BoundedEventSink` 抽取：timeout/threshold 可注入，`_put_event` 闭包薄委托
- [x] 满队列终态送达行为测试：边界/哨兵事件不因队列满被丢弃，有界等待后入队
- [x] 熔断降级：连续 N 次 undeliverable 后非终态事件立即丢弃计数（breaker_degraded），
      哨兵豁免、成功入队重置（TDD）
- [x] `backlog_stats` 增补订阅者队列深度 + `all_backlog_stats` + ops 端点
      `GET /api/v1/ops/stream-backlog`（TDD）
- [x] incident 形状专测：重连「明细丢失+终态在」即见终态不挂起
- [x] `record_drop` docstring 措辞修正（事件循环内精确、线程内尽力）
- [x] stub E2E 套件回归通过（SSE 流式链路无健康路径回归；23 passed / 3 @live skipped）
- [ ] 人工验证报告落 tests/validation/（真实管线 + 慢消费者场景抽查）
