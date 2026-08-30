# 调研：AG-UI + assistant-ui 接入（add-assistant-ui-thread Task 1）

- 日期：2026-08-30
- 分支：feat/design-system-download-center
- 范围：OpenSpec change `add-assistant-ui-thread` Task 1.1（版本锁定）+ 1.2（quick 模式事件形态与 AG-UI 事件映射表）
- 查证方式：PyPI / npm registry JSON API 实查（2026-08-30）、官方文档（docs.ag-ui.com、assistant-ui.com）、`ag_ui_langgraph` 0.0.44 wheel 源码解包审读；本仓库代码实读。

---

## TL;DR

1. **推荐版本组合**（详见 §1）：Python 侧只依赖 `ag-ui-protocol==0.1.21`（core 事件类型 + EventEncoder），**不引入 `ag-ui-langgraph`**；前端锁 `@ag-ui/client@0.0.59` + `@assistant-ui/react@0.15.17` + `@assistant-ui/react-ag-ui@0.0.57`，React 18 兼容。
2. **最大风险（结构性）**：design.md 决策 2 的前提不成立——quick 模式**不是 LangGraph graph**，而是自研 harness ReAct Agent（`agent_factory.build_agent(mode="quick")`，design.md 提到的 `build_quick_graph()` 不存在）。官方 `ag_ui_langgraph.LangGraphAgent` 只接受 `CompiledStateGraph`，无法包装 harness Agent；且 `ag-ui-langgraph` 的依赖链（`langchain>=1.2.0` → `langgraph<1.1.0`）与本仓 `langgraph 1.2.0` 直接冲突。因此后端应走「ag-ui-protocol 官方类型 + 薄翻译层」路线（约百行级），而非官方 LangGraph 适配层。
3. quick 模式**带工具调用**（web_search，TESTING=1 时为 stub），事件形态为 THINK / TOOL_CALL / TOOL_RESULT / ANSWER 交错，可完整映射到 AG-UI `REASONING_*` / `TOOL_CALL_*` / `TEXT_MESSAGE_*` 事件（映射表 15 行，见 §2）。

---

## 1. 版本锁定（Task 1.1）

所有版本号于 2026-08-30 经 PyPI / npm registry JSON API 实查。

### 1.1 Python 侧

| 包 | 最新版 | 发布日期 | 关键依赖 | 结论 |
|---|---|---|---|---|
| `ag-ui-protocol` | **0.1.21** | 2026-08-27 | `pydantic>=2.11.2`（Python >=3.9） | **推荐引入，锁 `==0.1.21`**。wheel 仅含 `ag_ui.core`（events/types/capabilities）+ `ag_ui.encoder`（EventEncoder），零 langchain/langgraph 依赖，与现有栈无冲突 |
| `ag-ui-langgraph` | 0.0.44 | 2026-08-27 | `ag-ui-protocol>=0.1.21`、`langchain>=1.2.0`、`langchain-core>=0.3.0`、`langgraph>=0.6.0,<2`、`pydantic>=2.0.0`；extra `fastapi`：`fastapi>=0.115.12`（Python >=3.10,<3.15） | **不引入**，两个原因见下 |

**不引入 `ag-ui-langgraph` 的原因**：

1. **API 不匹配**：`LangGraphAgent.__init__(*, name, graph: CompiledStateGraph, ...)` 只接受 LangGraph 编译图，内部经 `graph.astream_events(**kwargs)`（v2 事件流）消费（`ag_ui_langgraph/agent.py:2369/2443`，0.0.44 wheel 实读）。quick 模式的执行体是 harness `Agent`（`src/finance_agent/harness/loop.py` 的 ReAct 循环，litellm 直连，非 LangChain Runnable），其 token/工具事件不会出现在 `astream_events` 中——包装进单节点图也无法被适配层捕获。
2. **依赖冲突**：`langchain 1.2.0` 声明 `langgraph>=1.0.2,<1.1.0`，与本仓已锁 `langgraph 1.2.0`（pyproject `langgraph>=0.4.0`，实装 1.2.0）冲突。若走该路线须同步升级 `langgraph>=1.2.11` + `langchain 1.3.18`（当前最新，其约束为 `langgraph>=1.2.11,<1.3.0`），牵动 langchain-core 1.4.0 兼容面——PoC 阶段不值得。

**本仓现有 Python 版本（实查 `uv pip list`）**：fastapi 0.140.7 ✓（满足适配层 extra 约束，备用路线可用）、langgraph 1.2.0、langchain-core 1.4.0、litellm 1.85.1、pydantic 2.13.4 ✓（满足 `ag-ui-protocol>=2.11.2`）、starlette 1.3.1。

**后端推荐实现形态**：`POST /api/agui/quick` 内直接消费 `agent.run()` 产出的 `StreamEvent`，手工翻译为 `ag_ui.core.events` 的官方事件对象，经 `ag_ui.encoder.EventEncoder`（与官方 `add_langgraph_fastapi_endpoint` 同一编码器，endpoint.py 实读确认）编码为 SSE。协议类型与序列化仍是官方 SDK（版本演进由 SDK 承担），自研面收窄为翻译函数本身。Task 2.1 的 tasks 描述「官方 LangGraph 适配层包装」应据此修订（建议走 openspec-update-change）。

> 备用路线（如未来把 quick 改写为真 LangGraph 图）：`ag-ui-langgraph==0.0.44` + `add_langgraph_fastapi_endpoint(app, agent, path)` + `LangGraphAgent.clone()`（每请求隔离状态），但须先解决上述 langgraph/langchain 升级链。

### 1.2 前端侧

| 包 | 最新版 | 发布日期 | peerDeps | 结论 |
|---|---|---|---|---|
| `@ag-ui/client` | **0.0.59** | 2026-08-27 | 无 React peer（框架无关） | **锁 `0.0.59`**。deps：`@ag-ui/core`/`proto`/`encoder` 0.0.59、`rxjs@7.8.1`、`zod@^3.22.4`、`fast-json-patch`、`untruncate-json` |
| `@assistant-ui/react` | **0.15.17** | 2026-08-27 | `react ^18 \|\| ^19`、`react-dom ^18 \|\| ^19` | **React 18.3.1 兼容 ✓**。deps：`radix-ui@^1.6.7`（统一包，作为 dependency 而非 peer——与现有 shadcn 组件无 peer 冲突）、`zustand@^5`、`zod@^4`、`assistant-cloud`、`assistant-stream@^0.3.40` |
| `@assistant-ui/react-ag-ui` | **0.0.57** | 2026-08-27 | `react ^18 \|\| ^19` | **锁 `0.0.57`**。deps：`@ag-ui/client@^0.0.58`（与 0.0.59 兼容 ✓）、`@assistant-ui/core@^0.3.16`、`@assistant-ui/react-generative-ui@^0.0.16` |

**对接方式（官方文档 assistant-ui.com/docs/runtimes/ag-ui/overview + quickstart 实查）**：无独立桥接包命名空间混淆问题——runtime 适配器就是 `@assistant-ui/react-ag-ui` 的 `useAgUiRuntime({ agent })`，agent 为 `@ag-ui/client` 的 `HttpAgent({ url })`（POST RunAgentInput JSON、Accept SSE、`abortRun()` 中止）。适配器基于 `ExternalStoreRuntime` 分层，自动解析 `TEXT_MESSAGE_*`/`TOOL_CALL_*`/`REASONING_*`/`STATE_*` 事件为 assistant-ui 消息模型。三包组合即为官方推荐：

```bash
npm install @assistant-ui/react @assistant-ui/react-ag-ui @ag-ui/client
```

### 1.3 版本矩阵与潜在冲突

| 检查项 | 状态 |
|---|---|
| React 18 兼容 | ✓ `@assistant-ui/react@0.15.17` 与 `@assistant-ui/react-ag-ui@0.0.57` peer 均为 `^18 \|\| ^19`（npm 实查） |
| Radix 冲突 | 无 peer 冲突；`@assistant-ui/react` 依赖统一包 `radix-ui@^1.6.7`，现有 shadcn 原语（refactor-ui-design-system 引入）不受影响 |
| **Tailwind 版本** | ⚠ assistant-ui 官方 shadcn registry 组件面向 **Tailwind v4**（官方安装文档要求 tw-animate-css + v4 CSS-first 配置；本项目为 tailwindcss 3.4.17）。缓解：不复制官方 registry 样式组件，仅用 assistant-ui primitives + design-system 令牌自写样式（与 design.md 决策 3「theme 对齐」一致） |
| **zod 双版本** | ⚠ `@ag-ui/client` 用 zod ^3、`@assistant-ui/react` 用 zod ^4，npm 下双份并存。边界（HttpAgent ↔ runtime adapter）由 react-ag-ui 内部消化，理论低风险，实施时验证 |
| langchain/langgraph | 引入 `ag-ui-protocol` 无影响（仅 pydantic）；`ag-ui-langgraph` 路线见 §1.1 冲突说明 |
| 版本演进速度 | ⚠ 两生态每周发版（本次三包与后端两包均为 2026-08-27 发布）。tasks 已锁定精确版本，升级另立 change（design 风险 3） |

**未确认项**：无。所有包名/版本均经 registry 实查；`useAgUiRuntime` 选项、`fromAgUiMessages`、`add_langgraph_fastapi_endpoint`、事件 payload 字段均经官方文档或 wheel 源码确认。

---

## 2. quick 模式事件形态 → AG-UI 事件映射表（Task 1.2）

### 2.1 quick 模式 graph（实为 harness Agent）事件形态

- **执行体**：`build_agent(mode="quick")`（`src/finance_agent/agent_factory.py:916`）→ harness `Agent`（ReAct 循环，`max_iterations=3`，工具 = web_search（TESTING=1 时 `_stub_web_search`），LLM 经 LiteLLM/StubLLMClient 直连）。**非 LangGraph 图**。
- **事件源**：`agent.run(user_input)` 异步产出 `StreamEvent`（`src/finance_agent/harness/types.py:214`，`ActionType` 枚举 ：34）：`THINK`（DeepSeek reasoning_content 增量）、`THINK_TO_ANSWER`、`THINK_REPLACE`、`TOOL_CALL`、`TOOL_RESULT`、`ANSWER`（最终回答增量）、`ERROR`、`PROGRESS`、`TOOL_METADATA`。
- **现有 SSE 映射**：`stream_agent_to_sse`（`agent_factory.py:1198`）→ `chat_token` / `thinking_token` / `tool_call` / `tool_result` / `search_start` / `search_result` / `error` / `chat_done`（heartbeat 为 SSE 注释行）。
- **带工具调用**：是。quick 模式含 web_search 工具调用（思考 → web_search → 思考 → 回答；StubLLMClient `STUB_SCENARIO=tool_call` 确定性复现）。`THINK_TO_ANSWER`/`THINK_REPLACE` 为纠偏类事件（流末判定/后处理替换），映射时需特殊处理（见表）。

### 2.2 事件映射表

AG-UI 事件字段定义来自官方 docs（docs.ag-ui.com/sdk/python/core/events）：BaseEvent 共有 `type/timestamp/raw_event/metadata`；`TextMessageStartEvent{message_id, role:"assistant"}`、`TextMessageContentEvent{message_id, delta}`（delta 校验非空）、`ToolCallStartEvent{tool_call_id, tool_call_name, parent_message_id?}`、`ToolCallArgsEvent{tool_call_id, delta}`、`ToolCallResultEvent{message_id, tool_call_id, content, role:"tool"?}`、`ReasoningMessageStartEvent{message_id, role:"reasoning"}`、`ReasoningMessageContentEvent{message_id, delta}`、`RunStartedEvent{thread_id, run_id, input?}`、`RunFinishedEvent{thread_id, run_id, result?}`、`RunErrorEvent{message, code?}`、`MessagesSnapshotEvent{messages}`、`CustomEvent{name, value}`。

| # | harness StreamEvent（quick） | 现有 SSE | → AG-UI 事件 | payload 映射 | 自动/自定义 |
|---|---|---|---|---|---|
| 1 | run 开始（`agent.run()` 首个事件前） | 无 | `RUN_STARTED` | `thread_id=session_id`、`run_id=uuid4` | **自定义**（翻译层产出） |
| 2 | `ANSWER` 首个增量 | `chat_token` | `TEXT_MESSAGE_START` | `message_id`（本轮分配）、`role="assistant"` | **自定义** |
| 3 | `ANSWER` 后续增量 | `chat_token` | `TEXT_MESSAGE_CONTENT` | `message_id` 同上、`delta=event.content`（须非空） | **自定义** |
| 4 | 回答流结束（后续 THINK/工具或 run 结束） | （由 chat_done 收口） | `TEXT_MESSAGE_END` | `message_id` 同上 | **自定义** |
| 5 | `THINK` 首个增量 | `thinking_token` | `REASONING_MESSAGE_START` | `message_id`、`role="reasoning"` | **自定义** |
| 6 | `THINK` 后续增量 | `thinking_token` | `REASONING_MESSAGE_CONTENT` | `message_id`、`delta` | **自定义** |
| 7 | 思考流结束 | （隐式） | `REASONING_MESSAGE_END` | `message_id` | **自定义** |
| 8 | `THINK_TO_ANSWER` | 前端流内转换 | 关闭当前 `REASONING_MESSAGE_*` 段 + 打开 `TEXT_MESSAGE_START` | message_id 换段 | **自定义**（AG-UI 无等价事件） |
| 9 | `THINK_REPLACE` | 前端替换 | `REASONING_MESSAGE_START`（新段，replace 语义）+ content | 或累计重发；**未确认** assistant-ui 对 replace 的呈现，实施时验证 | **自定义** |
| 10 | `TOOL_CALL` | `tool_call`（+web_search 时 `search_start`） | `TOOL_CALL_START` + `TOOL_CALL_ARGS` | `tool_call_id=uuid4`、`tool_call_name=tc.name`、`args` 序列化为 `delta`（一次全量 JSON） | **自定义** |
| 11 | `TOOL_RESULT` | `tool_result`（+web_search 时 `search_result`） | `TOOL_CALL_RESULT` | `tool_call_id` 同上、`content=tr.output`（文本）；结构化搜索结果可附 `CUSTOM{name:"search_result", value:...}` 供 generative UI | **自定义** |
| 12 | `ERROR` | `error` | `RUN_ERROR` | `message=event.content` | **自定义** |
| 13 | 正常结束 | `chat_done`（+调用方 `done`） | `RUN_FINISHED` | `thread_id`、`run_id`、`result` 可省 | **自定义** |
| 14 | （无对应）历史初始化 | journal 重放 + chat_history 重建 | `MESSAGES_SNAPSHOT`（可选） | `messages` = session_store chat_history 映射（§3.3） | **自定义**；或前端走 history adapter（推荐，见 §3.3） |
| 15 | 心跳（10s 空闲） | `: heartbeat` 注释行 | SSE 注释行（非协议事件，保留） | — | 保留现有机制 |

> 参考（备用路线的官方自动映射）：`ag_ui_langgraph@0.0.44` 源码中，`on_chat_model_stream` 文本 chunk → `TEXT_MESSAGE_START/CONTENT/END`；`AIMessageChunk.tool_call_chunks` → `TOOL_CALL_START/ARGS/END`；`on_tool_end` → `TOOL_CALL_RESULT`；reasoning content → `REASONING_MESSAGE_*`；`on_custom_event` → `CUSTOM`；异常 → `RUN_ERROR`；末尾 → `RUN_FINISHED`。上表 1–13 与该语义一致，佐证映射表方向正确。

### 2.3 持久化一致性挂钩（供 Task 2.2/2.5）

「分块拼接 == 落库全文」的保证点：AG-UI 端点内**与翻译同步**累积 ANSWER 增量（等价 `_ChatCollector`：`response += delta`，仅收 `TEXT_MESSAGE_CONTENT` 的 delta），run 结束（RUN_FINISHED 前）/异常（RUN_ERROR 前）/客户端断开（CancelledError → `[输出中断]` 占位）时经 `upsert_chat(session_id, "assistant", response, ...)` 落库——复用 `_run_chat_task`（`api.py:1293`）的既有模式：`append_chat(user)` 任务开始落库 → 每 10s `_upsert_assistant_chat` → 终态落库 + `update_session_status`。`registry`/`StreamRegistry` 与 AG-UI 通道完全解耦（双轨隔离：AG-UI 端点不 publish 进 journal；Task 2.4 的隔离测试据此设计）。

---

## 3. 现有代码对接点清单

### 3.1 后端（quick 流式 + 落库挂钩点）

| 对接点 | 位置 | 说明 |
|---|---|---|
| quick 模式现有 SSE 端点 | `src/finance_agent/api.py:1757` `POST /api/chat`（`quick_chat`） | 新会话创建（`create_chat_session`）→ `registry.start(_run_chat_task)` → `GET /api/sessions/{session_id}/stream`（api.py:774）经 `_subscribe_sse`（api.py:1214）订阅转发；409 `session_busy` single-flight |
| 事件产生 | `_run_chat_task`（api.py:1293）→ `build_agent(mode=quick/follow-up)` → `stream_agent_to_sse`（agent_factory.py:1198） | AG-UI 端点复用 `build_agent` + `agent.run()`，替换 SSE 翻译 sink 为 AG-UI 翻译（Langfuse `react_loop` span 包裹逻辑需同步保留或等价迁移） |
| user 消息落库 | `_run_chat_task` 内 `append_chat(session_id, "user", req.message)`（api.py:1322） | AG-UI 通道同样在任务内落库（409 时不落） |
| assistant 落库 | `_ChatCollector`（api.py:1144）+ `_upsert_assistant_chat`（api.py:1188，每 10s upsert）+ `_persist_interrupted`（api.py:1277） | 「分块拼接 == 落库全文」挂钩点；AG-UI 端点等价实现（§2.3） |
| 状态流转 | `update_session_status`（running/completed/interrupted/failed，api.py:1324-1368） | AG-UI 通道沿用 |
| RunAgentInput 映射 | — | `thread_id→session_id`、`messages`（前端回传的历史，可直接注入 agent 上下文或忽略、由 `_inject_chat_history`（agent_factory.py:1108）从 session_store 重建——推荐后者，与现有语义一致）、`forwardedProps` 可承载 `llm_config`/`api_key`（未确认官方 schema 外字段兼容性，实施时以 HttpAgent 透传验证） |
| TESTING=1 | `_make_llm_client`（agent_factory.py:1067）返回 StubLLMClient；stub web_search（agent_factory.py:85） | AG-UI 端点必须走同一注入路径，E2E 才能确定性复现 |
| 会话取消 | `POST /api/sessions/{session_id}/cancel`（api.py:756）→ `registry` 任务取消 | AG-UI 通道的后台任务应挂入同一取消路径（或文档化为 PoC 限制） |

### 3.2 前端（quick 渲染边界 + 切换守卫）

| 对接点 | 位置 | 替换/保留 |
|---|---|---|
| quick 消息渲染分支 | `frontend/src/App.tsx:1252-1310`（`MessageItem` 内 `msg.type === 'chat'`：`agentTimeline`→`TimelineRenderer` 横幅 + `ReactMarkdown` 渲染 `chatResponse` + streaming cursor `data-testid="stream-status"`） | **替换**：quick/chat 视图改为 assistant-ui `Thread` + `useAgUiRuntime`；`showThinking` 对应思考段呈现 |
| 发送入口 | `quickChat`（App.tsx:516）/ `handleSendFromChat`（App.tsx:553） | 替换为 runtime 的发送路径（HttpAgent `runAgent`）；409 `session_busy` 提示语义需在 runtime `onError` 等价实现 |
| 深度/管线渲染 | `msg.type === 'pipeline' / 'report'`（App.tsx:1312+）、TimelineRenderer | **保留不动**（双轨隔离） |
| 现有流状态管理 | `frontend/src/stores/streamStore/index.ts`（`submit` :146、`switchSession` :259、`abortAll` :107、`hasActiveReader` :92、resume :297）+ `reduce.ts` | streamStore 保留服务深度模式；quick 新通道不共享（design 风险 4：守卫需在 runtime 层重实现） |
| **切换守卫（中止 + 快照恢复）** | 切换：`selectSession`（App.tsx:393）→ `store.switchSession(sessionId)`（index.ts:259，abort 当前 reader，live 在途消息保留后台写，非 live 置 pending 触发 `loadSession + rebuildSession`）；刷新：`store.abortAll()`（App.tsx:478 beforeunload） | AG-UI 通道等价实现：切换时 `HttpAgent.abortRun()`（官方 API，§1.2）+ 快照恢复走 §3.3；assistant-ui `onCancel` 回调（runtime-options 实查）挂守卫逻辑 |
| 历史快照轮询兜底 | App.tsx:572+（恢复态 2s 轮询） | quick 模式无管线快照，不涉及 |

### 3.3 历史消息结构 → AG-UI MessagesSnapshot 映射

**存储 schema**（`src/finance_agent/session_store.py:627 append_chat` / `:710 upsert_chat`，sessions 表 `chat_history` TEXT JSON 数组）：

```json
{ "role": "user" | "assistant", "content": "文本", "ts": "ISO 时间戳",
  "thinking": "思考原文（可选，仅 assistant）",
  "tool_calls": [{"name","args","result_text","done"}]（可选）,
  "agentTimeline": [TimelineItem...]（可选） }
```

**AG-UI `Message`**（ag_ui.core.types）：`{id, role: "user"|"assistant"|"system"|"tool", content, name?}`。

| chat_history 字段 | MessagesSnapshot 映射 |
|---|---|
| `role` | 直接映射 `user`/`assistant`（`id` 生成 uuid） |
| `content` | 直接映射 `content`（保证「落库全文 == 历史显示」） |
| `thinking` / `tool_calls` / `agentTimeline` | **无标准映射**。恢复侧两条路径：(a) 推荐——沿用现有 chat 会话 `rebuildSession` 重建（agentTimeline 横幅恢复语义不变，assistant-ui Thread 只接管新 run 的渲染，历史以现有 MessageItem 列表呈现 + Thread 仅增量）→ 若 Thread 必须接管全列表则 (b) `fromAgUiMessages`（`@assistant-ui/react-ag-ui` 官方导出，runtime-options 文档实查）+ `adapters.history.load()` 只映射 role/content，过程字段降级丢弃（PoC 验收点，需在 spec 明示） |
| AG-UI 侧历史回传 | `HttpAgent` 每次运行回传 `RunAgentInput.messages`；后端可忽略（历史已由 `_inject_chat_history` 从 session_store 注入 agent 上下文），双源不冲突 |

---

## 4. 风险备注（供 design/tasks 修订与实施计划）

1. **【最大·结构性】适配层前提不成立**：quick 模式是 harness Agent 而非 LangGraph graph；`ag_ui_langgraph` 无法包装且有 langgraph/langchain 版本冲突（§1.1）。design.md 决策 2 与 tasks 2.1 表述需修订为「ag-ui-protocol 官方事件类型 + EventEncoder + 薄翻译层」。这仍保住「协议标准化」的核心收益（类型、编码器、前端三包全官方），自研面仅剩 ~百行翻译函数（§2.2 十五行映射）。
2. **Tailwind v4 vs 3.4**（§1.3）：assistant-ui registry 组件面向 v4；缓解已述。
3. **版本演进快**：全部锁精确版本（`ag-ui-protocol==0.1.21`、`@ag-ui/client@0.0.59`、`@assistant-ui/react@0.15.17`、`@assistant-ui/react-ag-ui@0.0.57`）。
4. **守卫新实现面**（design 风险 4 确认）：`switchSession` 语义（index.ts:259）需在 `HttpAgent.abortRun()` + `useAgUiRuntime({onCancel})` 上重实现并补测试；live 在途「后台继续生成 + 切回恢复」在 AG-UI 通道缺失对应物（run 易逝），PoC 语义按「中止即中断落库（`_persist_interrupted` 等价）」设计，tasks 3.3 验证。
5. **zod 3/4 双份**（§1.3）：实施时在 pnpm/npm 树验证无运行时冲突。
6. **THINK_TO_ANSWER / THINK_REPLACE** 无 AG-UI 等价事件：映射表 #8/#9 的处理需在事件契约测试（Task 2.2）中固化；若 assistant-ui 对 reasoning 段 replace 呈现异常，可在 quick 模式禁用 DSML 清理路径（回退方案）。
7. **TextMessageContentEvent delta 非空校验**：空 delta（heartbeat 空转等）须过滤，否则 SDK 抛 ValidationError。
8. **TESTING=1 全链路**：AG-UI 端点必须复用 `_make_llm_client` 注入路径（§3.1），E2E 门禁（Task 4.2）依赖 stub 场景在 AG-UI 通道同样确定性。
