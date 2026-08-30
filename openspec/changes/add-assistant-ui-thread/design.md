# Design: add-assistant-ui-thread

## 决策

1. **双轨而非替换**：AG-UI 端点（`POST /api/agui/quick`）与现有 `/api/stream` 并行。理由：管线时间线的领域事件（思考标题、工具调用横幅、5 层 pipeline 快照）没有标准 AG-UI 事件可映射，强行塞进 `CUSTOM`/`STATE_DELTA` 等于换一种方式手搓协议；quick 对话是纯文本流，恰好在 AG-UI 标准事件覆盖范围内。PoC 验收后再评估管线事件的映射方案（另立 change）。
2. **协议类型用官方 SDK、翻译层自写（Task 1 调研后修订）**：~~使用官方 LangGraph 适配层~~ → 调研证实该前提不成立：quick 模式并非 LangGraph graph，而是 harness ReAct Agent（`agent_factory.py`），`ag_ui_langgraph@0.0.44` 只接受 `CompiledStateGraph`（内部走 `astream_events`，harness StreamEvent 不可见）；且其依赖 `langchain>=1.2.0` 会约束 `langgraph<1.1.0`，与本仓 `langgraph 1.2.0` 冲突。故采用：**`ag-ui-protocol==0.1.21`（仅依赖 pydantic）提供 `ag_ui.core` 事件类型 + `EventEncoder`（SSE 编码），harness StreamEvent → AG-UI 事件用自写薄翻译层**（15 行映射表见 docs/superpowers/research/2026-08-30-agui-assistant-ui-research.md）。协议类型与编码仍走官方包，自研范围收敛到一层纯函数翻译（可全量单测）。
3. **前端渲染替换、流管理最小化**：assistant-ui Thread + `@ag-ui/client`（HttpAgent → SSE）承担渲染与消息状态；会话切换守卫沿用现有语义（切换时中止当前 run + 快照恢复），不引入 CopilotKit 全家桶（scope 收敛，只取协议 + 渲染）。视觉层直接用 design-system 令牌给 assistant-ui 做 theme 对齐。
4. **历史恢复走快照而非事件回放**：AG-UI 的 `MessagesSnapshot` 用于运行前初始化消息列表（把 session_store 的 chat_history 映射为 Thread 初始消息），刷新/切回恢复仍走现有 session_store 快照路径——不改变已验证的恢复语义。

## 风险

- **双轨期边界蔓延**：管线事件可能被诱惑「顺手」迁过来 → 以 spec「双轨隔离」Requirement 硬约束（回退场景验证）。
- **assistant-ui 渲染结构与现有测试选择器耦合**：部分 quick 模式渲染测试可能因 DOM 结构变化失配 → spec 允许「等价迁移 + 清单记录」，深度模式测试零修改是硬线。
- **版本演进快**：AG-UI 与 assistant-ui 均快速迭代 → 依赖版本在 tasks 中锁定，升级另立 change。
- **切换守卫的新实现面**：assistant-ui runtime 的消息状态与 streamStore 不共享，切换中止/快照恢复需在 runtime 层重新实现并补测试，不能假设现有守卫自动生效。

## 开放问题（实施时决策）

- ~~quick 模式 graph 当前是否输出工具调用事件？~~ 已确认（Task 1）：quick 模式带 `web_search` 工具调用，harness StreamEvent 有对应 TOOL_CALL_START/ARGS/RESULT 事件 → 映射为 AG-UI `TOOL_CALL_START/ARGS/END`，渲染用 assistant-ui 工具 UI（映射表见调研文档）。
- ~~quick graph 事件形态差异？~~ 已确认（Task 1）：quick 模式非 LangGraph graph（实为 harness ReAct Agent），事件映射按调研文档 15 行映射表执行；无 LangGraph 适配层可用（见决策 2）。
