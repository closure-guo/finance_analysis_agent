## 1. Phase 0: 复现与基线

- [ ] 1.1 确认"双会话并发错乱"当前是否可复现（seq 竞态修复后）
- [ ] 1.2 跑全量现有测试（27 个）确认全绿，作为行为基线
- [ ] 1.3 从 Langfuse 或后端日志抓取 3 次完整 run 的 SSEEvent 序列，整理为 reduce 单测 fixture（落 tests/fixtures/）

## 2. Phase 1: reduce 纯函数

- [ ] 2.1 新建 `frontend/src/stores/streamStore/types.ts`：定义 `StreamPhase`、`SessionStreamState`、IDLE_STATE 常量
- [ ] 2.2 新建 `frontend/src/stores/streamStore/reduce.ts`：定义 `reduce(state, event)` 纯函数签名与骨架
- [ ] 2.3 搬运 session_created / parsing / resolved / stock_resolved 分支（store 层处理 session_created，不进 reduce）
- [ ] 2.4 搬运 analysis_start / node_start / node_complete / node_timing 分支（复用 pipelineTree.ts）
- [ ] 2.5 搬运 thinking_token / thinking_replace / thinking_to_answer 分支（复用 timeline.ts）
- [ ] 2.6 搬运 tool_call / tool_result 分支（复用 timeline.ts）
- [ ] 2.7 搬运 search_start / search_result / search_error 分支（复用 timeline.ts）
- [ ] 2.8 搬运 report_chunk / report_ready 分支
- [ ] 2.9 搬运 chat_token / chat_done 分支（复用 timeline.ts closeAllThinking）
- [ ] 2.10 搬运 awaiting_input / done / interrupted / error 分支
- [ ] 2.11 每个分支搬运后跑对应现有测试（timelineRenderer、agentTimeline、multiline-list-stream 等）
- [ ] 2.12 编写 reduce 单测：覆盖全部 24 种事件 + 典型事件序列 fixture 测试

## 3. Phase 2: StreamStore 与连接层

- [ ] 3.1 实现 `frontend/src/stores/streamStore/index.ts`：StreamStore 类骨架（streams Map、listeners Set、activeReader）
- [ ] 3.2 实现 subscribe / getSnapshot（useSyncExternalStore 契约，IDLE_STATE 引用稳定）
- [ ] 3.3 实现 applyEvent：seq 守门（去重 + 空洞检测）+ reduce + emit
- [ ] 3.4 实现 pump：SSE 读取循环，单读取器保证（abort 旧 reader 并等待退出）
- [ ] 3.5 实现 resume：after_seq 续传 + 204 处理
- [ ] 3.6 实现 submit：POST /api/analyze、POST /api/chat，response body 交给 pump
- [ ] 3.7 实现 switchSession：abort 旧 reader → GET 会话详情 → 重建 messages → 条件 resume
- [ ] 3.8 实现 cancel：POST cancel + 本地 abort
- [ ] 3.9 编写 store 时序测试：双会话并发流交错到达 → 各自 state 正确
- [ ] 3.10 编写 store 时序测试：流式中 switchSession → 切回 → 状态完整
- [ ] 3.11 编写 store 时序测试：seq 乱序/重复到达 → 去重正确
- [ ] 3.12 编写 store 时序测试：resume 遇 204 → phase 正确收口
- [ ] 3.13 编写 store 时序测试：abort 旧 reader 证明单读取器保证

## 4. Phase 3: 组件迁移

- [x] 4.1 实现 `frontend/src/stores/streamStore/useSessionStream.ts`：useSyncExternalStore 封装
- [x] 4.2 实现 `getStreamStore()` 模块级单例
- [x] 4.3 App.tsx 消息渲染块迁移到 useSessionStream
- [x] 4.4 App.tsx pipeline 渲染块迁移到 useSessionStream
- [x] 4.5 App.tsx 报告渲染块迁移到 useSessionStream
- [x] 4.6 App.tsx 输入提交迁移到 store.submit()
- [x] 4.7 App.tsx 会话切换迁移到 store.switchSession()
- [x] 4.8 每块切换后跑全量测试
- [x] 4.9 核销删除清单：streamRegistryRef、commitMessages、messagesRef 等 19 个 ref
- [x] 4.10 核销删除清单：saveCurrentStreamState / getStreamState / resumeAfterSeqFromSnapshot / ensureSingleReader / msgIdToClearOnReaderExit / isCurrentViewEvent / shouldProcessFetchedSession
- [x] 4.11 核销删除清单：3 处手写 getReader() 循环
- [x] 4.12 验证 App.tsx 主组件逻辑 ~490 行（全文件 1554 行含 1060 行纯 UI 子组件）、主组件 useRef 4 个

## 5. Phase 4: 守卫测试核销与收尾

- [x] 5.1 followup-sse-dedup 通过（集成测试全绿）；concurrent-subscription-seq-loss 自包含不依赖 App，保留通过
- [x] 5.2 select-session-stale-guard / select-session-last-seq 改写为 store 行为测试（switchSession 原子协议、rebuildSession lastSeq 规则）
- [x] 5.3 followup-resume-after-switch / restore-session-on-refresh 通过（集成测试全绿，验证 resume 续传链路）
- [x] 5.4 single-reader-invariant 改写为 StreamStore 结构保证测试（submit/resume/switchSession/cancel 单读取器）
- [x] 5.5 session-created-ref-sync 改写为 session_created key 迁移测试（ref 已删，语义进 store）
- [x] 5.6 streamingCursorLifecycle 依赖 timeline 纯函数（游标逻辑复用），保留通过
- [x] 5.7 保留 timelineRenderer / agentTimeline / pipelineTree / eta 等纯函数测试不动
- [x] 5.8 保留组件冒烟测试（smoke、SearchBanner 等），全部通过
- [x] 5.9 全量测试通过（28 文件 227 用例），新增 reduce/store 测试覆盖原被删守卫守护的场景

## 6. 场景验收

- [ ] 6.1 双会话同时流式运行，快速来回切换 10 次 → 两会话内容各自完整，无串话、无丢字
- [ ] 6.2 流式进行中刷新页面 → 恢复后从断点续传，无重复、无缺失
- [ ] 6.3 流式进行中取消 → 立即停渲染，后端任务终止，会话状态 interrupted
- [ ] 6.4 澄清流程：awaiting_input → 回答 → 继续分析，全程无异常

## 7. 文档与归档

- [ ] 7.1 更新 OpenSpec frontend/spec.md（sync delta）
- [ ] 7.2 新增 ADR：前端流状态所有权外置（人工落 docs/adr/）
- [ ] 7.3 更新 docs/incidents/ 事故记录：本次根因与结构性修复
- [ ] 7.4 人工验证报告落 tests/validation/
- [ ] 7.5 archive 前置检查：tasks.md 全勾 + verification 通过 + E2E 门禁通过
