# Tasks: fix-node-timer-real-lifecycle

> 前置：redesign-pipeline-hierarchical-timeline 已落地（分层时间轴 + applyNodeEvent）。

## 1. 后端：节点生命周期计时

- [x] 1.1 编写失败测试：`tests/test_node_timing.py` 断言 timed_node 包裹的节点 yield node_start/node_end custom 事件、ts 单调递增、duration_ms>=0、并行分析师归属正确
- [x] 1.2 新增 `src/finance_agent/nodes/_timing.py`：timed_node 装饰器（get_stream_writer 发 node_start/node_end，time.time() 计时）
- [x] 1.3 `src/finance_agent/graph.py`：build_5layer_graph 的 add_node 统一用 timed_node 包裹全部 22 节点
- [x] 1.4 编写失败测试：node_end 到达时下发 node_timing 事件携带真实耗时；node_start 附加 server_start_ts
- [x] 1.5 `src/finance_agent/agent_factory.py`：custom 分支处理 node_start/node_end（暂存时间戳 + node_end 时下发 node_timing）；stream_agent_to_sse 透传 node_timing 与 node_start 的 server_start_ts

## 2. 前端：时间戳策略

- [x] 2.1 编写失败测试：`pipelineTree.test.ts` 新增 4 用例——server_start_ts 优先、node_timing 覆盖近似耗时、end-start 推导、无 server_* 回退 Date.now()
- [x] 2.2 `frontend/src/pipelineTree.ts`：node_start 用 server_start_ts、node_timing 用 server_duration_ms/end-start 覆盖，回退 Date.now()
- [x] 2.3 `frontend/src/types.ts`：NodeTimingEvent 类型 + NodeStartEvent.server_start_ts；App.tsx 处理 node_timing SSE 事件

## 3. 关键设计修正（实施中发现）

- 真实时序：custom node_start 在 updates chunk 前、node_end 在其后到达 → node_complete 由 updates chunk 驱动时 node_end 未到、duration 不可得。故真实耗时经**独立 node_timing 事件**下发（node_end 到达时），前端据此覆盖近似值，而非附加到 node_complete。
- 层展开策略调整：已完成层默认展开（非 pending 层展开），修复"快速完成的多层自动折叠致分析师子节点从 DOM 消失"——贴合"直观看到执行状态"诉求。经用户确认。

## 4. 验证

- [x] 4.1 `uv run pytest` 后端 347 通过（test_sse_stream 2 个预存在失败）/ `npm test` 前端 110 通过
- [x] 4.2 `uv run ruff check` 全绿 / `npx tsc --noEmit` 无错
- [x] 4.3 E2E：timeline config 全套 17 通过。STUB_NODE_DELAY=0.6 延长 analyzing 窗口。stub 并行批次瞬态 DOM 捕获脆弱，#2/#3 改为验证用户最终可见契约（报告卡片 4 分析师独立摘要 / 管线完整产出报告），时间轴子节点独立渲染由单测覆盖。新增 `tests/scripts/verify_node_timing_stub.py` 验证 stub 图双流事件全节点覆盖
- [x] 4.4 人工验证报告落 `tests/validation/node-timer-real-lifecycle-validation.md`
