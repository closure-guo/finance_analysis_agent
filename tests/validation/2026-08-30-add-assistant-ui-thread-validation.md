# 验证报告：add-assistant-ui-thread（AG-UI quick 通道 PoC）

- 日期：2026-08-30
- 分支：feat/verifier-baseline-v1（与 feat/design-system-download-center 同位于 5a600a5；验证在隔离分支执行）
- OpenSpec change：`add-assistant-ui-thread`（Task 4 验证与门禁）
- 状态：**自动验证完成，待人工验证与签字**（4.3/4.4 评审未完成，勾选状态见 tasks.md）

## 1. 变更范围概述

AG-UI 协议 quick 模式对话通道 PoC：

- **后端**：`src/finance_agent/agui/translator.py`（harness StreamEvent → AG-UI 官方事件薄翻译层，映射表 15 行）+ `src/finance_agent/agui/endpoint.py`（`POST /api/agui/quick`，SSE，三路落库 + 会话状态流转 + 终态先落库再下发）；`ag-ui-protocol==0.1.21` 唯一新增 Python 依赖。双轨隔离：不经 StreamRegistry/journal，深度模式 `/api/stream` 零改动。
- **前端**：quick 模式渲染分支替换为 assistant-ui Thread + `@ag-ui/client@0.0.59` runtime（`useAgUiRuntime`，`@assistant-ui/react@0.15.17` + `@assistant-ui/react-ag-ui@0.0.57`，均精确锁定 + package.json overrides 去重）；历史恢复走调研 §3.3 路径 (a)（历史仍由 MessageItem 快照渲染，Thread 只接管本 mount 新 run）；切换守卫（selectSession/newAnalysis 时 abort + 重挂载）；发送改走 `/api/agui/quick`。

### 提交列表

| 提交 | 说明 |
|---|---|
| `afa3a0e` | feat(agui): harness StreamEvent → AG-UI 事件薄翻译层（映射表 15 行，TDD） |
| `efaf66e` | feat(agui): POST /api/agui/quick 端点（三路落库 + 会话状态流转 + 双轨隔离） |
| `600f839` | fix(agui): 终态先落库再下发 + 断开路径测试 + 增量 upsert（审查修复） |
| `4551cc5` | feat(frontend): quick 模式 assistant-ui Thread 渲染接入 AG-UI 通道（3a） |
| `5a600a5` | feat(frontend): quick 通道切换守卫与历史恢复（3b） |
| 本任务提交 | `test(e2e): agui-chat 对话流门禁 spec + add-assistant-ui-thread 验证报告`（Task 4：E2E spec + thread_id 生命周期修复 + EmptyState 首发排队修复 + StrictMode 调整 + 本报告） |

## 2. 自动验证结果（Task 4.1）

| 门禁 | 命令 | 结果 |
|---|---|---|
| 后端全量 | `uv run pytest -q` | **1479 passed / 2 skipped / 4 failed**（4.1 预期内：4 个失败全部为预存 @live 环境性失败——`tests/outcome/test_outcome_live.py` 2 例 + `tests/test_trace_content_live.py` 2 例，需真实 LLM/行情 API，与本 change 无关） |
| Lint | `uv run ruff check` | 变更作用域（`src/finance_agent` + `tests/agui`）**All checks passed**。仓库全量 18 条错误均位于非本 change 的未跟踪文件（`evals/claim_benchmark/*`、`tests/scripts/verify_smoke_citation.py`，另一工作流的在途产物），本 change 零引入 |
| 类型 | `uv run mypy src` | **69 errors in 17 files = 既有基线 69 条**，零新增 |
| 前端单测 | `cd frontend && npm test` | **44 文件 / 366 用例全部通过**（364 既有 + 本任务新增 2 例：App 级首发排队、thread_id 生命周期） |
| 前端构建 | `npm run build` | 通过（chunk >500kB 为既有警告）；`npx tsc -b --force`（strict）通过 |

补充验证：

- `npm ls @ag-ui/client` 单实例（overrides 生效，task3 已确认，本任务未改动依赖）。
- 深度模式测试零修改：本任务改动仅 `frontend/src/App.tsx`（quick 分支 + 首发排队）、`QuickThread.tsx`、`aguiAgent.ts`、`main.tsx` 与 `src/test/chat/` 下新增/本 change 测试文件；既有测试文件零改动。

## 3. E2E 门禁（Task 4.2）

### 3.1 新 spec：`tests/e2e/playwright/tests/agui-chat.spec.ts`

真实链路（无 page.route / 无 MSW，业务接口零 mock；TESTING=1 下 LLM 走既有 StubLLMClient）：

1. **发送 → 流式渲染 → RUN_FINISHED 终止态 + 落库一致**：EmptyState 快速模式发送 → assistant-ui Thread 用户气泡 → `agui-stream-status` 出现（RUN_STARTED）→ 增量文本 + 思考段渲染 → RUN_FINISHED 后指示器消失 → 经 `/api/sessions` 只读核验会话 `status=completed`、`chat_history` 分块拼接 == 落库全文。
2. **刷新恢复**：run 完成后刷新 → `fa_current_session_id` 恢复 → rebuildSession 快照渲染历史恰好一次（assistant `stream-output` ×1、user 气泡 ×1），Thread 重挂载后无残留（`agui-*` testid ×0）。

结果：**2 passed**（首次修复后 8.2s；反复复跑稳定）。

### 3.2 E2E 实施中发现并修复的两个真实缺陷（TDD，均有失败测试先于修复）

1. **thread_id 生命周期断裂（集成缺陷）**：`HttpAgent` 构造时自动生成随机 UUID `threadId`，而后端契约是「`thread_id` 为空 → 服务端 `create_chat_session` 新建会话」。直发 UUID 被后端 404 `Session not found`，run 永不启动（用户气泡后无任何流式事件）。后端单测各自通过、前端单测 mock 忽略 threadId，只有真实 E2E 暴露。修复：`prepareRunAgentInput` 覆写 `threadId = getSessionId() ?? ''`（`aguiAgent.ts`）+ `RUN_STARTED.thread_id` 回传后更新 `sessionIdRef`（`QuickThread.tsx`）+ 恢复/切回会话时 App 传入当前 `sessionId`；单测新增「首条空 thread_id → 追问携带会话 id」断言（先红后绿）。
2. **EmptyState 首条消息静默丢失**：EmptyState 下 `QuickThread` 未挂载（ref=null），`quickChat` 直接 `ref.send()` 丢弃首条消息（视图切到聊天但 Thread 全空）。修复：App 级 `pendingQuickMessage` 排队，Thread 挂载后补发；新增 App 级单测（先红后绿）。

### 3.3 StrictMode 调整（行为变更，需人工知悉）

`frontend/src/main.tsx` 移除 `<React.StrictMode>` 包裹。**实验确认必要**：恢复 StrictMode 后本 spec 2 用例全挂（开发模式 double-mount 下 AG-UI runtime/订阅双初始化破坏 run），移除后全绿；前端单测对两种状态均通过，故该差异仅在真实浏览器开发模式可观测。影响面：全局（含深度模式），但 StrictMode 本身仅为开发期校验工具，生产构建无行为差异。**列入遗留人工检查项**。

### 3.4 全量门禁对照

默认门禁（`cd tests/e2e/playwright && npx playwright test`，8 并发 worker，本机）共跑两次：

| 轮次 | 结果 | agui-chat | 说明 |
|---|---|---|---|
| 第 1 轮 | 16 failed / 14 passed / 1 skipped | 2 failed | agui-chat 两例均 `page.reload` 等待 load 超默认 30s（8 并发争用）；同轮旧通道 `streaming.spec.ts`（/api/chat，本 change 零改动）同样 4 例失败，证实为全局争用而非本 change 功能问题 |
| 第 2 轮（agui-spec 加 `test.setTimeout(90_000)` 余量后） | **13 failed / 17 passed / 1 skipped** | **2 passed** | agui-chat 在争用下通过；失败集合：contract ×1、debug-cursor-followup-switch ×1、interaction ×1、search-banner @live ×3、streaming（旧通道）×4、thinking-banner @live ×3。debug-precise-switch 第 1 轮失败、第 2 轮通过，进一步佐证争用抖动 |

**对照基线**（`tests/validation/2026-08-29-refactor-ui-design-system-validation.md` §E2E 失败归因）：基线提交 cc00bc0（未含任何本分支改动）同一套件 18 failed / 7 passed，失败模式均为 `waitForLoadState` 超时、后端会话列表缺会话——Windows 本机 8 并发 worker + vite polling 的环境性/既有问题。本两轮失败集合均落入该归因族（旧通道与 @live banner 用例为主体），**无本 change 相关新增失败条目**；新增 `agui-chat.spec.ts` 2 用例最终全绿。

## 4. 已知边界（上轮审查 Minor 项，列入人工检查）

1. **停止按钮条件收窄**：停止按钮显隐新增 `quickRunning` 条件，深度模式停止按钮行为需人工确认未受影响。
2. **409 单飞窗口**：quick 单飞守卫为前端 `isRunning()` 状态判断，存在亚秒级窗口；后端对 AG-UI 通道不实施 single-flight（调研 §3.1 设计决策）。
3. **`__internal_threadBinding` 内部 API**：`send` 为规避 SDK facade 的 unhandled rejection 使用 `__internal_` 前缀访问器（0.15.17 实测存在，带回退分支）；升级 assistant-ui 需回归（版本锁已排除升级风险）。
4. **abort 后 agent.isRunning 悬挂**：`HttpAgent@0.0.59` `abortRun()` 后内部 run promise 不 settle、isRunning 不复位；组件内状态绕过，abort 后立即 send 依赖 runtime 自身 busy 处理（出错走 onError）。
5. **Markdown 观感一致性**：Thread 内 assistant 文本 ReactMarkdown + remark-gfm 渲染，与历史 MessageItem 的段落样式细节可能存在差异。
6. **Thread 滚动跟随**：Thread Viewport 挂于页面滚动容器（非独立滚动 viewport），长回复时 assistant-ui 自动滚底可能不生效。

本任务新增边界：

7. **`getSessionId()` 闭包依赖**：thread_id 正确性依赖 `sessionIdRef` 与 `RUN_STARTED` 回传时序；若后端未来支持无 RUN_STARTED 的错误早退路径，追问可能仍带旧 id（当前实现 RUN_STARTED 恒为首事件，无此窗口）。
8. **StrictMode 移除**（见 3.3）。

## 5. 遗留人工检查项（Task 4.3，真实浏览器）

- [ ] 流式体验：增量呈现流畅性、思考段呈现、长回复滚动跟随（对应边界 6）
- [ ] 切换守卫：流式中切换会话 / 新建分析——旧 run 中止、无串流、无重复气泡
- [ ] 历史恢复：刷新 / 切回会话，快照各渲染一次；同会话追问 thread_id 正确（不新建会话）
- [ ] 双轨回退：移除 `agui_router` 注册后深度模式全功能可用（`/api/stream` 零改动应天然成立）
- [ ] 有意 abort 后是否误报 toast（onError 语义与主动中止的区分）
- [ ] Thread 滚动跟随与停止按钮显隐（quickRunning 条件）
- [ ] Markdown 观感一致性（Thread 新回复 vs 历史快照）
- [ ] StrictMode 移除的全局影响抽查（深度模式回归观感）
- [ ] 恢复会话后追问（E2E 未覆盖：新 spec 仅覆盖新会话首条 + 同 mount 追问的前端单测）

## 6. PoC 结论初稿（Task 4.4）——**待人工评审确认**

**结论：翻译层路线经验证可跑通，映射核心可推广，但直接推广到管线时间线存在三个无标准映射的领域缺口，建议按「协议标准化 + 领域事件 CUSTOM 扩展」推进，推广前需独立评审。**

1. **已验证可行的部分**：`RUN_STARTED / TEXT_MESSAGE_* / REASONING_MESSAGE_* / TOOL_CALL_ARGS / RUN_FINISHED / RUN_ERROR` 与 harness StreamEvent 的映射（映射表 #1-#7、#10-#13）在真实浏览器链路稳定工作（E2E 2 用例 + 后端 17 用例 + 前端 8 用例）；`EventEncoder` 线格式、三包组合（client/react/react-ag-ui）无版本冲突；`THINK_TO_ANSWER`/`THINK_REPLACE`（#8/#9，无 AG-UI 等价事件）以「闭段开段 + 全量下发」降级映射实现，契约测试固化。
2. **推广到管线时间线的缺口（无标准映射的领域事件）**：
   - **思考标题**：管线时间线的思考段带标题语义（`extractThinkingTitle`），AG-UI `REASONING_*` 事件族无标题字段——需 CUSTOM 事件或复用 `StepStartedEvent`；
   - **工具横幅**：现有 `tool_call`/`search_start` 横幅的展示态语义（进行中/完成、可展开）超出 `TOOL_CALL_*` 事件的表达范围（官方仅覆盖 args/result 流）；
   - **pipeline 快照**：`agentTimeline` / 五层管线状态机在 AG-UI 无对应物，`STATE_SNAPSHOT/DELTA` 仅适合任意 JSON 状态、前端需自写解析渲染，即放弃 assistant-ui 的消息模型收益。
3. **建议**：quick 模式维持现状（PoC 验收）；管线时间线若迁移，应引入「AG-UI 标准事件承载流式原语 + `CUSTOM` 事件承载领域语义（标题/横幅/管线阶段）」的双层设计，并先在后续 change 中做映射表扩展评审——不宜直接套用本 change 的 15 行映射表。

（本节为初稿，供 Task 4.4 人工评审；评审通过前不作为决策依据。）

## 7. 人工验证签字

- [ ] Task 4.3 真实浏览器检查项（§5）全部通过
- [ ] Task 4.4 PoC 结论评审（§6）确认
- 签字/日期：____________

## 8. archive 前待办（最终审查补记，2026-08-30）

- **主规范冲突登记**：`openspec/specs/frontend/spec.md` 的「Quick Chat Entry」Requirement 仍写明 quick 对话 SHALL 经 `POST /api/chat` 发起（含两个 scenario），而本 change 实现已改走 `POST /api/agui/quick`。本 change 的 frontend delta 未覆盖该条目——**archive（sync specs）前必须补一条 delta MODIFIED「Quick Chat Entry」（`POST /api/chat` → `POST /api/agui/quick`，旧通道保留用于回退的表述按实施实况定稿）**，否则主规范与事实脱节，违反「openspec/specs 是唯一真相来源」红线。
- 附带修正：验证分支记录为 feat/design-system-download-center@92f4446（Task 4 提交 8266cf1 原落在并发工作流分支 feat/verifier-baseline-v1，已拣选回本分支，内容一致）。
