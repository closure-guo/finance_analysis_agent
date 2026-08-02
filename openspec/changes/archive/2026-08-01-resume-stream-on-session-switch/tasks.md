# Tasks: resume-stream-on-session-switch

## 1. 后端持久化：session_events 表与状态枚举

- [x] 1.1 `session_store.py` `init_db()` 新增 `session_events` 表迁移（session_id、seq、event_json、created_at，`UNIQUE(session_id, seq)`）及索引
- [x] 1.2 新增 `append_session_event(session_id, event) -> seq`（会话内 seq 单调递增，executor 中执行避免阻塞事件循环）与 `list_session_events(session_id, after_seq) -> list[dict]`
- [x] 1.3 `delete_session` 级联删除该会话的 session_events
- [x] 1.4 `init_db()` 启动 reconcile：`UPDATE sessions SET status='interrupted' WHERE status='running'`
- [x] 1.5 验证：单测覆盖 append/list 的 seq 单调性、唯一约束、级联删除、reconcile（8 个测试全通过）

## 2. 后端 StreamRegistry：任务与订阅管理

- [x] 2.1 新增 `src/finance_agent/stream_registry.py`：`SessionStream`（task 句柄、订阅者队列列表、最后 seq）与全局 registry
- [x] 2.2 `start(session_id, coro) -> bool`：single-flight 判定，已有活跃任务返回 False；任务 finally 中必然注销
- [x] 2.3 `publish(session_id, event)`：先 `append_session_event` 落库，再 fan-out 到有界订阅者队列（容量 256）；满队列的订阅者断开
- [x] 2.4 `subscribe(session_id, after_seq)`：先重放 journal，再注册实时队列；无活跃任务时重放后补终态事件（interrupted/done）
- [x] 2.5 `cancel(session_id) -> bool`：`task.cancel()`，走中断兜底路径
- [x] 2.6 验证：单测覆盖 single-flight、断开不杀任务、慢订阅者断开、cancel 注销（7 个测试全通过）

## 3. 后端 API 改造：/api/analyze 与 /api/chat

- [x] 3.1 将 `event_stream`/`chat_stream` 的生成主体抽取为后台任务函数（`_run_react_analysis`/`_run_chat_task`），事件经 `registry.publish` 下发
- [x] 3.2 端点改为：session 创建/校验 -> single-flight 冲突返回 409 `session_busy` -> `registry.start` 提交任务 -> 返回订阅转发流
- [x] 3.3 后台任务 `finally`：CancelledError/异常时部分回复落库（标注 `[输出中断]`，保留 thinking/tool_calls）+ status=interrupted + publish interrupted 终态事件；处理后 re-raise CancelledError
- [x] 3.4 正常完成路径不变：collector 回复落库、focus/status 更新、done 事件（均经 publish 落 journal）
- [x] 3.5 user 消息落库时机校验：409 拒绝时 SHALL NOT 追加 user 消息
- [x] 3.6 验证：现有测试全通过（34 个测试），断连不杀任务由 StreamRegistry 保证

## 4. 后端新端点：恢复与取消

- [x] 4.1 `GET /api/sessions/{id}/stream`：解析 `after_seq` 参数与 `Last-Event-ID` 头（后者优先），经 `registry.subscribe` 返回 SSE 流；每 15s 心跳注释行防代理断连
- [x] 4.2 `POST /api/sessions/{id}/cancel`：调用 `registry.cancel`，无活跃任务返回 404
- [x] 4.3 `DELETE /api/sessions/{id}`：删除前先 `registry.cancel` 该会话活跃任务
- [x] 4.4 `GET /api/sessions` 列表返回字段确认包含 status（前端运行指示依赖）
- [x] 4.5 验证：现有测试全通过

## 5. 前端：per-session 流状态与订阅管理

- [x] 5.1 `App.tsx` 新增 `streamRegistryRef: Map<sessionId, StreamState>`（abort、pipelineMsg、streamingReport、lastSeq），替代全局单例
- [x] 5.2 `selectSession`：移除 `abortStreaming()` 杀任务语义，仅断开本地订阅；目标会话 status 为 running 时经恢复端点重连（携带 lastSeq）
- [x] 5.3 重放/实时事件与首发事件走同一 `handleSSEEvent`/`handleChatStreamEvent` 处理路径；`session_created`、`analysis_start`、pipeline 消息创建做幂等处理
- [x] 5.4 `newAnalysis`/`deleteSession` 同步调整：不再中断其他会话任务；删除当前会话经后端取消
- [x] 5.5 中断态 UI：interrupted 会话展示"输出已中断，可追问继续"标记，清除 streaming 转圈
- [x] 5.6 验证：TypeScript 编译零错误通过

## 6. 前端：运行指示与显式停止

- [x] 6.1 侧边栏会话条目：status 为 running 或本地有活跃订阅时显示"生成中"指示（呼吸灯），终态事件后移除
- [x] 6.2 输入区：当前会话运行中时提交新消息先拦截并提示"该会话正在生成中，可停止后再发"；收到 409 时同样提示
- [x] 6.3 新增"停止"按钮（流式区域）：调用 `POST /api/sessions/{id}/cancel`
- [x] 6.4 `beforeunload` 时断开本地订阅（仅退订）
- [x] 6.5 验证：TypeScript 编译零错误 + 133 个前端测试全通过

## 7. E2E 与收尾

- [x] 7.1 新增 session-switch E2E spec（`session-switch-resumption.spec.ts`）：中途切出再切回，断言内容继续增长
- [x] 7.2 E2E：显式停止后中断标记持久化（spec 中包含停止按钮测试）
- [x] 7.3 E2E：运行中会话拒绝新输入（spec 中包含输入拦截测试）
- [x] 7.4 修复 incident 012 的 2 个 deselect 测试：修复 MockLLMClient 缺少 `tool_choice` 参数 + 添加超时保护，2 个测试全通过，移除 ci.yml `--deselect`
- [x] 7.5 `uv run pytest` 36/36 通过、前端 Vitest 133/133 全绿
- [x] 7.6 部署文档注明单 uvicorn worker 约束（docker-compose.yml 注释 + AGENTS.md 架构速览）
- [ ] 7.7 手动新增 ADR："生成任务与 SSE 连接解耦 + 事件日志重放"（agent 不得自动新建，不阻塞归档）
- [ ] 7.8 手动新增 incident 记录：本次"切换会话输出中断"事故的根因与修复（关联 incident 012，不阻塞归档）
