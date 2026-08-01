# Proposal: fix-node-timer-real-lifecycle

## Why

分层时间轴（redesign-pipeline-hierarchical-timeline）落地后，节点计时在快速节点上恒为 `0:00`。

**根因**：LangGraph `updates` 流模式对每个节点只产出**一个 chunk**（节点完成后才发出）。后端 `_make_run_deep_analysis` 在消费该 chunk 时，于**同一循环迭代内**背靠背 yield node_start 与 node_complete，前端两个事件的 `Date.now()` 间隔 <1ms → `durationMs = max(0, ~0) = 0`。

慢节点（LLM 调用，秒级）不受影响——其 node_complete 在下一个 chunk 到达时才有真实间隔，故 Layer II 辩论节点计时正常，只有 PREP 的快速纯函数节点（check_cache/fetch_data 等）恒为 0。

**这是事件模型的根本限制**：node_start 与"节点产生输出"绑定在同一 chunk，无法从 updates 流推导节点的真实开始时刻。修复需要后端在节点真实生命周期的入口/出口发出带时间戳的事件。

## What Changes

- **后端节点生命周期计时**：新增 `timed_node` 装饰器统一包裹全部 22 个图节点，在节点入口/出口通过 `get_stream_writer()` 发出 custom 事件：
  - 入口：`{"type": "node_start", "node": <node_id>, "ts": <epoch_ms>}`
  - 出口：`{"type": "node_end", "node": <node_id>, "ts": <epoch_ms>, "duration_ms": <ms>}`
- **图流模式升级**：`graph.stream` 从 `stream_mode=["updates", "custom"]` 保持双模式（custom 已用于 thinking_token），新增处理 `node_start`/`node_end` 两种 custom payload。
- **SSE 透传**：`stream_agent_to_sse` 将 custom 的 node_start/node_end 透传为带**后端真实时间戳**的 SSE 事件（复用现有 `node_start`/`node_complete` 类型，新增 `server_ts` 字段）。
- **前端计时改用后端时间戳**：`applyNodeEvent` 优先使用事件携带的 `server_ts`（后端真实生命周期），缺失时回退 `Date.now()`（保持 stub/fast path 兼容）。快速节点因 node_start/node_end 在真实入口/出口发出，durationMs 反映真实耗时。

## Non-goals

- 不改变节点执行逻辑、重试、超时（纯计时观测，零侵入业务）。
- 不改变 updates 流的 node_complete 的 output 提取与 `completed`/`progress` 计算（仍在 updates chunk 到达时计算）。
- 不改变 fast path（`api.py` 直接 SSE 路径）——其节点本就是串行 await，node_start/node_complete 时间戳天然真实。
- 不改变前端分层时间轴组件结构，仅 `applyNodeEvent` 的时间戳来源策略。

## Alternatives Considered

| 方案 | 评估 |
|------|------|
| 快速节点不显示耗时 | 丢失观测信息，且用户明确要真实计时 |
| 前端预估倒计时 | 不真实，违背"计时器应反映真实耗时"的意图 |
| 改用 stream_mode="debug" 获取节点起止 | debug 流事件量大、结构不稳定，且与现有 updates 提取逻辑冲突，过度复杂 |
| **timed_node 装饰器 + custom 流（选定）** | 复用已验证的双模式流与 custom 通道，装饰器统一包裹零侵入，时间戳来自真实生命周期 |

## Affected Capabilities

| Capability | Change Type | Description |
|------------|-------------|-------------|
| `pipeline-events` | MODIFIED | 节点生命周期事件携带后端真实时间戳（新增 node_start/node_end custom 通道） |
| `frontend` | MODIFIED | 节点计时优先使用后端 server_ts，快速节点显示真实耗时 |

## Success Criteria

- [ ] 快速节点（如 check_cache）耗时显示真实值（非恒 0:00）；实际为毫秒级时显示 `0:00` 属正确（真实耗时 <1s），但 fetch_data 等网络节点应显示秒级真实耗时
- [ ] 慢节点（LLM）计时不受影响，仍显示真实耗时
- [ ] 后端 node_start/node_end 时间戳来自节点真实入口/出口（可在 Langfuse trace 与后端日志交叉验证）
- [ ] stub/fast path 兼容（无 server_ts 时回退 Date.now()，现有 E2E 不回归）

## Impact

- **代码**：`src/finance_agent/nodes/*.py`（装饰器包裹）、`graph.py`（节点注册处统一包裹）、`agent_factory.py`（custom 事件处理 + SSE 透传）、`frontend/src/pipelineTree.ts`（时间戳策略）
- **测试**：后端节点生命周期事件测试、前端 pipelineTree server_ts 用例、E2E 节点计时真实值断言
- **风险**：装饰器需在 Send 扇出的并行子图中正确工作（get_stream_writer 在并行节点各自独立）；需验证 custom 流与 updates 流的交错不破坏现有 thinking_token 分组
