## Why

真实 UI 全部走 ReAct 路径（前端 `startAnalysis` 从不传 `stock_code`），但当前仅 fast path 有 `PipelineRunner` 后台线程保护——SSE 断开后管线继续执行。ReAct 路径的 Agent 编排与 SSE 绑定在同一个 async generator 中，用户切换会话时前端调用 `AbortController.abort()` 中断 SSE，直接导致 Agent 编排被取消、管线结果无人消费，表现为"任务中断"。同时，LLM 调用失败时 `chat_stream` yield 错误文本而非 raise（静默失败）、ReAct 路径无心跳保护、无全局管线超时、前端轮询 5 分钟超时后提示"管线可能已中断"，共同构成"不明原因中断"现象。`pipeline-events/spec.md` 第 21 行已将 ReAct 路径后台化标记为"后续 change"待解决项。

## What Changes

- **ReAct 路径后台化**：将 ReAct 路径的深度分析管线执行与 SSE 订阅解耦——`run_deep_analysis` 工具内的 `graph.stream` 通过后台任务执行，SSE 断开后管线继续运行，结果持久化到会话；客户端切回时通过快照 + 轮询恢复
- **管线中断检测与恢复**：引入管线级超时机制，超时后会话标记为 failed 并记录中断原因；前端轮询恢复时展示中断原因而非仅提示"可能已中断"
- **LLM 调用错误传播**：`chat_stream` 最终失败时 SHALL raise 异常而非 yield 错误文本，使 Agent 主循环能正确捕获并处理，杜绝静默失败
- **ReAct 路径 SSE 心跳**：ReAct 路径的 SSE 流 SHALL 发送心跳注释（与 fast path 对齐），防止代理/浏览器因空闲超时断连
- **中断原因持久化**：会话 status 更新为 failed 时 SHALL 记录 `failure_reason` 字段，使前端能展示具体中断原因（超时/数据拉取失败/LLM 失败/Agent 异常）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `pipeline-events`: 将「管线后台执行与断点恢复」的适用范围从 fast path 扩展到 ReAct 路径；新增「管线超时与中断检测」requirement（全局超时 + 失败原因持久化 + 前端中断原因展示）

## Impact

- **后端核心变更**：
  - `src/finance_agent/agent_factory.py` — `_make_run_deep_analysis` 工具内 graph.stream 后台化、快照/结果持久化与 SSE 解耦
  - `src/finance_agent/agent_factory.py` — `stream_agent_to_sse` 增加心跳、错误传播改进
  - `src/finance_agent/harness/litellm_client.py` — `chat_stream` 最终失败 raise 而非 yield 错误文本
  - `src/finance_agent/harness/loop.py` — Agent 主循环对 LLM 异常的错误处理路径
  - `src/finance_agent/pipeline_runner.py` — 可能复用/扩展 PipelineRunner 为 ReAct 路径提供后台执行能力
  - `src/finance_agent/session_store.py` — 新增 `failure_reason` 列与写入逻辑
  - `src/finance_agent/api.py` — `/api/analyze` ReAct 路径 SSE 心跳、会话详情返回 `failure_reason`
- **前端变更**：
  - `frontend/src/App.tsx` — 轮询恢复时展示 `failure_reason`；轮询超时逻辑调整
- **依赖与风险**：ReAct 路径后台化涉及 async generator 生命周期管理，需确保 Langfuse Context 跨边界问题不恶化；SQLite 新增列需数据库迁移
