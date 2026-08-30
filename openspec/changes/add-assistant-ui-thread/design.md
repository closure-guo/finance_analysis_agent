# Design: add-assistant-ui-thread

## 决策

1. **双轨而非替换**：AG-UI 端点（`POST /api/agui/quick`）与现有 `/api/stream` 并行。理由：管线时间线的领域事件（思考标题、工具调用横幅、5 层 pipeline 快照）没有标准 AG-UI 事件可映射，强行塞进 `CUSTOM`/`STATE_DELTA` 等于换一种方式手搓协议；quick 对话是纯文本流，恰好在 AG-UI 标准事件覆盖范围内。PoC 验收后再评估管线事件的映射方案（另立 change）。
2. **后端用官方适配层而非手写翻译**：使用 AG-UI 官方 Python SDK 的 LangGraph 集成（`ag_ui_langgraph`，FastAPI endpoint 助手）包装现有 quick 模式 graph。理由：事件类型定义随 SDK 版本演进，手写翻译层会把「协议标准化」的收益重新变成自研维护负担。现有 LLM 配置（LLMConfig/llitlm 格式）在 graph 构建层注入，适配层不感知。
3. **前端渲染替换、流管理最小化**：assistant-ui Thread + `@ag-ui/client`（HttpAgent → SSE）承担渲染与消息状态；会话切换守卫沿用现有语义（切换时中止当前 run + 快照恢复），不引入 CopilotKit 全家桶（scope 收敛，只取协议 + 渲染）。视觉层直接用 design-system 令牌给 assistant-ui 做 theme 对齐。
4. **历史恢复走快照而非事件回放**：AG-UI 的 `MessagesSnapshot` 用于运行前初始化消息列表（把 session_store 的 chat_history 映射为 Thread 初始消息），刷新/切回恢复仍走现有 session_store 快照路径——不改变已验证的恢复语义。

## 风险

- **双轨期边界蔓延**：管线事件可能被诱惑「顺手」迁过来 → 以 spec「双轨隔离」Requirement 硬约束（回退场景验证）。
- **assistant-ui 渲染结构与现有测试选择器耦合**：部分 quick 模式渲染测试可能因 DOM 结构变化失配 → spec 允许「等价迁移 + 清单记录」，深度模式测试零修改是硬线。
- **版本演进快**：AG-UI 与 assistant-ui 均快速迭代 → 依赖版本在 tasks 中锁定，升级另立 change。
- **切换守卫的新实现面**：assistant-ui runtime 的消息状态与 streamStore 不共享，切换中止/快照恢复需在 runtime 层重新实现并补测试，不能假设现有守卫自动生效。

## 开放问题（实施时决策）

- quick 模式 graph 当前是否输出工具调用事件（web_search 等）？若有，AG-UI `TOOL_CALL_*` 事件天然覆盖，渲染用 assistant-ui 的工具 UI——在 tasks 的事件契约测试中固化。
- LangGraph 适配层与现有 `agent_factory.build_quick_graph()` 的输出 event 形态差异（messages vs updates 模式）需在 Task 1 调研后定实现细节。
