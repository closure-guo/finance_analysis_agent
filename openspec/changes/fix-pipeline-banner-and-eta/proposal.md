# Proposal: fix-pipeline-banner-and-eta

## Why

深度分析管线与快速模式共存在三类 UI 行为缺陷，严重影响用户对执行状态的感知：

1. **思考/工具调用横幅不自动关闭**：快速模式下思考完成后横幅仍停留；深度分析管线下因后端 agent 路径缺失 `node_start` 事件，前端 `currentNode` 长期为空，节点思考横幅的活动/完成切换不可靠。
2. **`~90s` 预估时间静态不变**：前端硬编码静态文案，无倒计时逻辑；incident 008 实测管线总耗时约 258s，预估严重失真。
3. **Layer II 进度长时间无反馈**：Layer II 含 5 个串行 LLM 子节点（bull_r1/bear_r1/bull_r2/bear_r2/research_manager），缺少 `node_start` 事件导致 6 阶段圆点与进度文案停滞，用户感知"卡死"。

上述问题均为**意图不变的 bug 修复**（spec 契约已写明 node_start 行为，实现漂移），本 delta 先行修复，为后续管线 UI 分层时间轴重设计（独立 delta）奠定事件流基础。

## What Changes

- **后端补发 `node_start` 事件**：`agent_factory.py` 的 `_make_run_deep_analysis` 流式工具在 `graph.stream` 迭代到节点 updates chunk 时，先 yield `node_start`（携带 node/layer/desc），再 yield `node_complete`；保证 6 阶段圆点与 `currentNode` 能正确进入 running 态。
- **前端横幅显式关闭**：
  - 快速模式：`thinking_token` 停止且 `chat_token`/`tool_call` 开始、或收到 `chat_done`/`done` 时，将末尾 thinking banner 置为完成态折叠。
  - 管线模式：`node_start` 到达时更新 `currentNode`；`node_complete` 到达时将该节点 timeline 的 thinking banner 显式置为完成态折叠，不再仅依赖 `current === node` 隐式切换。
- **动态 ETA 替换静态 `~90s`**：移除硬编码文案，改为"已用时长 + 预估剩余时间"。预估基于历史运行数据（localStorage 记录最近 N 次管线总耗时，取中位数；无历史时回退为固定默认值 240s），随已完成进度线性收敛。
- **修复 spec 漂移**：更新 `frontend` spec 的 `Pipeline Progress Display` 需求，明确 agent 路径与 fast path 均 SHALL 发 `node_start`；新增横幅显式关闭与动态 ETA 的需求契约。

非目标（out of scope，留待后续 delta）：管线 UI 分层时间轴重设计、Layer I 卡片摘要错位（fundamental 卡片显示技术面文案）的内容修复、辩论层并行化架构优化（incident 008）。

## Capabilities

### New Capabilities

（无新增 capability）

### Modified Capabilities

- `frontend`:
  - 修改 `Pipeline Progress Display`：明确 agent 路径亦 SHALL 发 `node_start`；新增节点运行中显示已用时长的场景。
  - 修改 `Pipeline Thinking Display`：新增"node_complete 后该节点思考横幅显式折叠"的场景。
  - 修改 `Conversation Stream Common Events`：新增"思考完成前收到回答 token/工具调用时末尾思考横幅折叠"的场景。
  - 新增需求 `Pipeline ETA Display`：动态预估剩余时间的契约。

## Impact

**受影响代码**：

- 后端：
  - `src/finance_agent/agent_factory.py`（`_make_run_deep_analysis`、`_stream_graph`、`stream_agent_to_sse` 增加 node_start 透传）
  - `src/finance_agent/api.py`（SSE 序列化无需改动，事件类型已存在）
- 前端：
  - `frontend/src/App.tsx`（`handleSSEEvent` 处理 node_start、`PipelineCard` ETA 组件、`ThinkingBanner` 关闭逻辑）
  - `frontend/src/timeline.ts`（thinking banner 显式完成态标记）
  - `frontend/src/TimelineRenderer.tsx`（按显式完成态而非仅 isLast 判定折叠）
  - `frontend/src/types.ts`（无需新增事件类型，复用现有 `node_start`）
- 测试：
  - `tests/` 新增/更新 node_start 事件流单测与 ETA 计算单测
  - E2E：更新管线进度断言（tests/e2e/）
- 文档：`openspec/specs/frontend/spec.md` 经 sync 合并 delta

**兼容性**：事件协议不变（复用已定义的 `node_start` 事件），fast path 行为不变，旧会话历史数据不受影响。

**风险**：agent 路径与 fast path 的事件序列需保持一致；ETA 预估算法需避免频繁跳动（采用平滑收敛）。
