# Design: fix-pipeline-banner-and-eta

## Context

当前系统存在三条相互关联的 UI 缺陷链：

1. **事件流缺口**：深度分析走 agent 路径（`agent_factory._make_run_deep_analysis`），`graph.stream` 迭代中只把 updates chunk 映射为 `StreamEvent.progress` → SSE `node_complete`；fast path（`api._run_graph_streaming`）则成对发送 `node_start`/`node_complete`。前端 `openspec/specs/frontend/spec.md` 的 `Pipeline Progress Display` 契约明确要求 node_start，属于实现漂移。
2. **横幅关闭机制依赖隐式状态**：前端 `TimelineRenderer` 以"item 是否为 timeline 末尾且消息仍 streaming"判定 ThinkingBanner 活动态；管线模式下又依赖 `currentNode === node`。由于 node_start 缺失，`currentNode` 长期为空，节点思考横幅无法正确切换完成态。快速模式下思考横幅关闭也仅靠后续 item 顶出末尾的副作用。
3. **ETA 硬编码**：`App.tsx` 中 `~90s` 为静态字符串，incident 008 实测管线总耗时约 258s。

本设计为 bug 修复 delta（意图不变），为后续"管线 UI 分层时间轴"重设计 delta 提供完整的事件流基础。

## Goals / Non-Goals

**Goals:**

- agent 路径与 fast path 事件序列对齐：每个图节点均发 `node_start` + `node_complete`
- 思考/工具调用横幅在其工作完成后**显式**折叠，不再依赖隐式位置推断
- 用动态 ETA（已用时长 + 预估剩余）替换静态 `~90s`
- 修复 spec 与实现的漂移

**Non-Goals:**

- 不改变管线 UI 的整体布局结构（6 阶段圆点保留，分层时间轴属下一 delta）
- 不做辩论层并行化等后端架构优化（incident 008 记录，另行立项）
- 不修改事件协议格式（复用已有 `node_start` 类型定义）
- 不处理 Layer I 分析师卡片摘要文案错位的内容问题

## Decisions

### D1: node_start 在 agent 路径的注入点

**决策**：在 `agent_factory._make_run_deep_analysis` 的 `graph.stream` 迭代中，当某个节点的 updates chunk **首次**出现时，先 yield `StreamEvent.node_start(node, layer, desc)`，再按原逻辑 yield progress。用 `startedNodes: set[str]` 去重，避免同一节点多轮更新（如 bull_r2 chunk 包含 bull_r2 本身）重复发 start。

**备选**：在 `stream_agent_to_sse` 侧由 PROGRESS 事件反推 node_start——被否决，因为该层拿不到"节点首次出现"的时序，且会让 harness 层承载图结构知识。

**备选**：改前端用 node_complete 反推 running 态——被否决，治标且无法显示"当前节点运行中"。

### D2: 横幅显式完成态标记

**决策**：给 thinking 类型 `TimelineItem` 增加 `done?: boolean` 字段：

- 对话流：收到 `tool_call`、首个 `chat_token`、`thinking_to_answer`、`chat_done`/`done`、`error` 时，将末尾未完成 thinking item 置 `done=true`
- 管线流：收到 `node_complete` 时，将该 node 对应 timeline 的末尾 thinking item 置 `done=true`；收到新节点的 `thinking_token` 时，将其他节点未完成的 thinking item 置 `done=true`（防御性收口）
- `TimelineRenderer` 活动态判定改为 `!item.done && isLast && streaming`（对话流）/ `!item.done && current === node`（管线流）

工具调用横幅已有 `done` 字段（`tool_result` 置位），无需改动，仅需确保管线模式下 tool_result 正确路由（现状已支持）。

**备选**：引入显式 `thinking_done` 事件——被否决，增加协议复杂度，前端从现有事件足以推断。

### D3: 动态 ETA 算法

**决策**：

- 管线启动时记录 `startTime`；每次 `node_complete` 记录 `(completedCount, elapsedMs)` 快照
- 预估总时长 `estimatedTotal`：取 localStorage `pipelineDurations`（最近 10 次完整运行耗时）的中位数；无历史时用默认值 240_000ms
- 剩余时间 = `max(0, estimatedTotal - elapsed)`，但当实际进度比例 `p = completed/total` 超过 `elapsed/estimatedTotal` 时，用 `elapsed / p` 重新估算总时长（线性外推收敛），避免后期严重超估
- 展示格式："已用时 1:23 · 预计剩余 ~2:10"，每秒刷新；完成后写入 localStorage
- 节点级：当前 running 节点显示该节点已运行时长（由 node_start 时间戳驱动）

**备选**：按阶段加权 ETA（每层历史耗时分别统计）——被否决为过度设计，Layer II 重设计后再评估。

### D4: ETA 历史存储

**决策**：localStorage 键 `financeAgent.pipelineDurations`，JSON 数组，最多保留 10 条，管线完成（`report_ready`）时写入。纯前端实现，不新增后端接口。

## Risks / Trade-offs

- [agent 路径补发 node_start 后，前端 6 阶段圆点 running 态切换频率变高，可能出现闪烁] → node_start/node_complete 成对到达，状态转移单调（pending→running→completed），无回退；E2E 验证
- [fast path 与 agent 路径事件序列分叉风险] → 抽取共享的"节点首次出现判定"逻辑或分别实现但以同一单测约束两条路径的事件序列
- [ETA 初期无历史数据时不准] → 默认值取 incident 008 实测量级（240s），并在 UI 上用 `~` 前缀明示是估计值
- [localStorage 不可用时 ETA 失效] → 回退默认值，功能不阻塞

## Migration Plan

纯增量行为修复，无数据迁移。部署顺序：后端先发（多发 node_start 对旧前端无害，旧前端忽略未知/未处理事件字段）、前端后发。

## Open Questions

- 无。
