# add-assistant-ui-thread Implementation Plan（Tasks 2-4）

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development。本计划以 Task 1 调研文档为需求权威源：**docs/superpowers/research/2026-08-30-agui-assistant-ui-research.md**（下称「调研文档」），映射表/对接点行号/版本号一律以它为准。

**Goal:** quick 模式对话接入 AG-UI 协议端点 + assistant-ui 渲染（PoC），深度模式/管线时间线零影响。

**Architecture:** 后端 `ag_ui.core` 官方类型 + `EventEncoder` + harness StreamEvent 薄翻译层（新模块 `src/finance_agent/agui/`）；前端 `@assistant-ui/react` + `@assistant-ui/react-ag-ui` + `@ag-ui/client`，quick/chat 渲染分支替换为 Thread，深度模式继续走 streamStore。

**Tech Stack:** Python: ag-ui-protocol==0.1.21（仅 pydantic 依赖）；前端: @ag-ui/client@0.0.59、@assistant-ui/react@0.15.17、@assistant-ui/react-ag-ui@0.0.57（精确锁定，React 18.3.1 兼容已验证）。

## Global Constraints

- spec 权威：`openspec/changes/add-assistant-ui-thread/specs/chat-stream/spec.md` + `specs/frontend/spec.md`
- 深度模式/管线通道**零改动**：`/api/stream`、StreamRegistry、streamStore、TimelineRenderer 不动；现有测试零修改通过（前端 quick 渲染用例允许等价迁移并记录清单）
- 「分块拼接 == 落库全文」：ANSWER 增量与翻译同步累积，终态/异常/断开三种路径都落库（复用 `_run_chat_task` 模式，见调研文档 §2.3）
- TESTING=1 全链路：AG-UI 端点必须复用 `_make_llm_client` 注入路径（stub web_search 确定性复现）
- TextMessageContentEvent delta 非空（空增量必须过滤，否则 SDK ValidationError——调研文档风险 7）
- 心跳保留 SSE 注释行机制（非协议事件）
- 版本锁精确值，升级另立 change

---

### Task 1: 后端依赖 + 翻译层（TDD）

**Files:**
- Modify: `pyproject.toml`（`uv add ag-ui-protocol==0.1.21`）
- Create: `src/finance_agent/agui/__init__.py`、`src/finance_agent/agui/translator.py`
- Test: `tests/agui/__init__.py`、`tests/agui/test_translator.py`

**Interfaces:**
- Produces: `async def translate_to_agui(events: AsyncIterator[StreamEvent], thread_id: str, run_id: str) -> AsyncIterator[BaseEvent]`
- 语义：按调研文档 §2.2 映射表（15 行）实现，含状态机（当前 text/reasoning 段开闭）、THINK_TO_ANSWER 换段（#8）、THINK_REPLACE 新段（#9）、TOOL_CALL 分配 tool_call_id 且 ARGS 一次全量（#10）、ERROR→RUN_ERROR（#12）、空 delta 过滤。
- 实现约束：纯函数级可测（不依赖 FastAPI）；事件对象用 `ag_ui.core.events` 官方类型。

**Steps:**
1. `uv add ag-ui-protocol==0.1.21`；确认 `uv tree` 无 langchain/langgraph 新约束。
2. 写失败测试：脚本化 StreamEvent 序列（从 `harness/types.py` 构造）→ 断言产出 AG-UI 事件类型序列与关键字段。用例至少覆盖映射表 #1-#13：纯文本对话完整序列；思考→回答换段（THINK_TO_ANSWER）；工具调用（TOOL_CALL/TOOL_RESULT → TOOL_CALL_START/ARGS/RESULT + id 一致性）；ERROR → RUN_ERROR；空 ANSWER 增量被过滤；THINK_REPLACE 新段。
3. 跑红 → 实现 translator → 跑绿。
4. `uv run ruff check && uv run mypy src tests/agui`（mypy 对比基线 69 条无新增）。
5. Commit: `feat(agui): harness StreamEvent → AG-UI 事件薄翻译层（映射表 15 行，TDD）`

### Task 2: 后端端点 + 持久化（TDD）

**Files:**
- Create: `src/finance_agent/agui/endpoint.py`（APIRouter）
- Modify: `src/finance_agent/api.py`（`app.include_router`，一行挂载；其余不动）
- Test: `tests/agui/test_endpoint.py`

**Interfaces:**
- Produces: `POST /api/agui/quick`，请求体 AG-UI `RunAgentInput`（thread_id 可空——为空则服务端 `create_chat_session` 新建会话，thread_id 从 RUN_STARTED 事件回传）；SSE 响应（EventEncoder 编码）。
- 语义（对接点见调研文档 §3.1，行号为准确引用）：
  - 会话创建/404 校验（thread_id 给定但不存在 → 404）
  - `build_agent(mode="quick")`（TESTING=1 走同一 stub 注入）+ `agent.run()`；Langfuse `react_loop` span 逻辑等价保留
  - user 消息 `append_chat`（任务内）；assistant 落库等价 `_ChatCollector`：累积 TEXT_MESSAGE_CONTENT delta，终态（RUN_FINISHED 前）/异常（RUN_ERROR 前）/CancelledError（`[输出中断]` 占位，`_persist_interrupted` 等价）三路落库 + `update_session_status`
  - **不 publish 进 registry/journal**（双轨隔离，调研 §2.3）
  - 取消：挂入现有 `POST /api/sessions/{session_id}/cancel` 路径（取消 → 任务 CancelledError → 中断落库）
- 实现约束：SSE 用 EventEncoder 编码；心跳沿用注释行机制；endpoint 不 import registry。

**Steps:**
1. 写失败测试（TestClient，monkeypatch `build_agent` 返回脚本化 stub agent + 真实 translator）：
   - 正常序列：流事件类型顺序 RUN_STARTED → TEXT_MESSAGE_* → RUN_FINISHED；分块拼接 == 落库 assistant 全文（调研 §2.2 场景 1）
   - LLM 异常（stub agent 抛 ERROR 事件）→ RUN_ERROR 终止 + 不落库成功回复（场景 2）
   - thread_id 不存在 → 404
   - thread_id 为空 → 新建会话且 RUN_STARTED.thread_id 非空
   - 用户消息落库
2. 跑红 → 实现 endpoint → 跑绿。
3. 双轨隔离：`uv run pytest tests/ -q` 全量——现有 `/api/stream` 契约测试（tests/test_api_* 族）必须零修改通过；`git diff` 确认 api.py 仅 +include_router 一处。
4. `uv run ruff check && uv run mypy`（无新增）。
5. Commit: `feat(agui): POST /api/agui/quick 端点（三路落库 + 会话状态流转 + 双轨隔离）`

### Task 3: 前端 assistant-ui 渲染（分 3a/3b 两个提交）

**Files:**
- Modify: `frontend/package.json`（三包精确锁定）
- Create: `frontend/src/chat/aguiAgent.ts`（HttpAgent 工厂：url=/api/agui/quick、headers 带 LLM 配置）+ `frontend/src/chat/QuickThread.tsx`（assistant-ui Thread，design-system 令牌样式，不用官方 registry 组件——Tailwind v4 风险，见调研 §1.3）
- Modify: `frontend/src/App.tsx`（quick/chat 渲染分支 `msg.type === 'chat'` 处接入；发送路径 `quickChat` 改走 AG-UI 通道；切换守卫）
- Test: `frontend/src/test/chat/`（新目录）

**Interfaces:**
- `QuickThread({ sessionId, onRunFinished })`：内部 `useAgUiRuntime({ agent: HttpAgent })`；历史初始化走调研 §3.3 路径 (a)——现有 MessageItem 列表渲染历史，Thread 只接管新 run（推荐路径，agentTimeline 横幅语义不变）
- 切换守卫：`selectSession` 触发 `agent.abortRun()`（官方 API）→ 后端 CancelledError → 中断落库；切回快照恢复走现有 rebuildSession
- 深度模式分支零改动

**Steps（3a）:**
1. `npm install @ag-ui/client@0.0.59 @assistant-ui/react@0.15.17 @assistant-ui/react-ag-ui@0.0.57 --save-exact`
2. 写失败测试（`frontend/src/test/chat/quickThread.test.tsx`，HttpAgent fetch mock——组件级 mock 允许，E2E 不 mock）：发送 → Thread 渲染流式增量（SSE 事件脚本）→ RUN_FINISHED 后指示器消失
3. 实现 aguiAgent.ts + QuickThread.tsx + App.tsx 接线 → 绿
4. Commit: `feat(frontend): quick 模式 assistant-ui Thread 渲染接入 AG-UI 通道（3a）`

**Steps（3b）:**
1. 写失败测试：切换守卫（流式中切会话 → abortRun 被调 + 切回快照渲染不重复）；历史恢复（旧消息 MessageItem 呈现 + 新 run 进 Thread）；409 busy 语义在 runtime onError 等价呈现
2. 实现 → 绿
3. 全量 `npm test`：深度模式测试零修改；quick 渲染旧用例如需等价迁移，逐条记录清单（spec 允许）
4. Commit: `feat(frontend): quick 通道切换守卫与历史恢复（3b）`

### Task 4: 验证与门禁

- [ ] `uv run pytest -q` 全量 + ruff + mypy（基线对比）；`npm test && npm run build`
- [ ] E2E 新 spec `tests/e2e/playwright/tests/agui-quick-chat.spec.ts`（不 mock 业务接口；TESTING=1 stub 链路）：发送 → 流式呈现 → 完成 → 刷新恢复；深度模式回归抽查（现有 spec 通过数不减少）
- [ ] 人工验证报告 `tests/validation/2026-08-30-add-assistant-ui-thread-validation.md`（流式体验/切换守卫/历史恢复/双轨回退四项 + PoC 结论评审 4.4）
- [ ] tasks.md 勾选（人工验证项除外）
