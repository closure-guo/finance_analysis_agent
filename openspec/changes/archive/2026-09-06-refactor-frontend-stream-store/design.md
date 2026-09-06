## Context

前端 `App.tsx` 目前 3518 行，持有 22 个 `useState`、19 个 `useRef`、1 个手写 `streamRegistryRef: Map<sessionId, StreamState>`。流状态（SSE 连接、事件缓冲、消息拼接、seq 游标、流归属）由 App 组件亲自持有，同一事实存在三份拷贝，靠 `commitMessages()` 手工同步。约 100 处 `setXxx` 散落在事件处理器中，任何处理器都能写任何状态。

后端事件日志已就绪（`resume-stream-on-session-switch` delta 已完成）：`session_events` 表按 session 内单调递增 seq 落库，`GET /api/sessions/{id}/stream` 支持 `after_seq` 断点续传，`sessions.status` 提供终态回执。前端快照层已从"必要"变成"冗余且有害"。

`src/test/` 下 27 个测试文件中至少 10 个在守护流式并发的时序正确性，每修一个 bug 加一道守卫，守卫之间产生新的交互 bug。

## Goals / Non-Goals

**Goals:**

1. 流状态所有权从 App 组件迁移到独立的 `StreamStore`（单一写入者、单一事实源）
2. 组件对流状态只读订阅（`useSyncExternalStore`），删除全部 ref 镜像与手工同步代码
3. 会话切换 / 刷新恢复一律走后端 replay，前端不再保存消息快照
4. 状态变化逻辑收拢为 `reduce(state, event)` 纯函数，可脱离 React 单测
5. 单读取器结构性保证：`single-reader-invariant` 从测试守护的约定变成不可能违反的结构

**Non-Goals:**

- 不迁移到 `@langchain/langgraph-sdk`（后端协议不兼容，改造成本失控）
- 不引入 XState 等状态机库（流式数据状态不是状态机的适用场景）
- 不改后端事件协议（已达标；gap 事件暂不需要，日志无 TTL 清理）
- 不重写 UI 组件（Sidebar / ReportCard / Charts / PipelineTimeline 保留）
- 不更换框架（保持 React 18 + Vite，不迁 Next.js）
- 本阶段不引入 React Query（列为后续独立迭代）

## Decisions

### D1: 自研 StreamStore 而非引入 langgraph-sdk

**选择**: 自研 `StreamStore`（约 300~400 行）

**理由**: 后端协议为自定义 timeline 协议；SDK 绑定 LangGraph Server 协议，兼容层工程量失控。DeerFlow 的模式不绑定 LangGraph 协议，可用少量代码复制该模式骨架。

**替代方案**: `@langchain/langgraph-sdk` `useStream` hook — 需要后端改造成 LangGraph Server 协议，成本不可控。

### D2: `useSyncExternalStore` 而非 Context + useState

**选择**: `useSyncExternalStore` 封装订阅

**理由**: 官方为"React 外部可变源"设计的订阅 API；避免 tearing；快照引用稳定即可正确工作。

**替代方案**: Context + useState — 需要 Provider 包裹，且无法避免 tearing 问题。

### D3: 事件按 sessionId 分流写入，而非全局判断"是否当前视图"

**选择**: `Map<sessionId, SessionStreamState>`，事件按 sessionId 写入对应 state

**理由**: 归属判断从运行时检查变为数据结构保证，消除串话类 bug 的整个类别。迟到的事件写进它该去的会话，天然不会污染当前视图。

**替代方案**: 现有 `streamingSessionIdRef` + `isCurrentViewEvent` 运行时判断 — 已被证明会产生守卫交互 bug。

### D4: 前端不存消息快照，切回一律后端重建 + replay

**选择**: 非活跃会话的 `messages` 在切换时丢弃，切回时从后端重建（`GET /api/sessions/{id}` 拿历史 + `stream?after_seq=` 补在途事件）

**理由**: 后端事件日志已是事实源；双事实源互相打架是残留 bug 的来源之一。

**替代方案**: 保留前端快照作为兜底 — 两套事实源互相打架，正是当前 bug 再生的根因。

### D5: seq 空洞显式 resync，不静默跳过

**选择**: `applyEvent` 检测 `seq > lastSeq + 1` 时触发一次 `resume(after_seq=lastSeq)` 补齐；补齐失败降级为刷新会话详情

**理由**: 借鉴 DeerFlow gap 事件思想；静默降级是并发错乱"必然发生"的机制。

**替代方案**: 静默跳过 — 会导致消息缺失，且难以排查。

### D6: 逐分支搬运 + 行为等价验证，而非重写事件逻辑

**选择**: 把 App.tsx 中现有的事件处理 switch 逐分支搬运进 reduce，每个分支搬运后立即跑对应现有测试验证行为等价

**理由**: 现有事件处理包含大量已修 bug 的隐性知识，重写会丢失它们。

**替代方案**: 重写事件处理逻辑 — 会丢失已修复 bug 的隐性知识，引入新 bug。

### D7: `phase` 取代 `appState` 中与会话相关的部分

**选择**: `StreamPhase` 类型（idle/connecting/streaming/awaiting_input/resuming/done/interrupted/error）取代 `appState` 的 'analyzing' / 'clarifying'

**理由**: 会话生命周期状态与全局 UI 状态分离；全局 UI 状态（如侧边栏开关）不进 store。

**替代方案**: 保留 `appState` 作为唯一状态 — 继续混淆会话状态与 UI 状态。

## Risks / Trade-offs

| 风险 | 概率 | 缓解措施 |
|------|------|----------|
| R1: reduce 搬运时行为漂移（某个分支遗漏隐式副作用） | 中 | Phase 0 fixture 先行；逐分支搬运 + 即时测试；搬完一块跑全量 |
| R2: seq 空洞（后端跳号）在 replay 中暴露 | 低 | applyEvent 检测 `seq > lastSeq+1` 时不静默跳过：触发一次 resume 补齐；补齐失败降级为刷新会话详情 |
| R3: 刷新恢复依赖 localStorage 的 sessionId，与后端 status 不一致 | 低 | switchSession 时以后端 SessionDetail.status 为准（interrupted/failed 直接定型，不发起 resume） |
| R4: 高频 token 事件导致渲染压力 | 低 | store 内做微批（同一次事件循环的多个事件合并为一次 emit）；`useSyncExternalStore` 快照引用稳定避免无效渲染 |
| R5: 重构期间新 bug 引入主分支 | 中 | 分支开发 + Phase 粒度 PR；CI 全量测试门禁（现有分支保护已配置） |

## Migration Plan

### Phase 0: 复现与基线

- 确认"双会话并发错乱"当前是否可复现（seq 竞态修复后）
- 现有 27 个测试全部跑绿，作为行为基线
- 整理 SSEEvent 24 种事件的实际出现顺序样本（从 Langfuse 或后端日志抓 3 次完整 run），作为 reduce 单测的 fixture

### Phase 1: reduce 纯函数

- 新建 `stores/streamStore/reduce.ts` 与 `types.ts`
- 逐事件分支从 App.tsx 搬运迁移逻辑，复用 `timeline.ts` 纯函数
- 每个分支搬运后跑对应现有测试
- 产出：reduce 单测覆盖全部 24 种事件 + 典型事件序列 fixture 测试

### Phase 2: StreamStore 与连接层

- 实现 `StreamStore`：subscribe/getSnapshot/applyEvent/pump/resume/submit/switchSession/cancel
- store 级时序测试（不渲染 React，直接驱动 store）
- 产出：store 单测套件（新增约 8~10 个测试）

### Phase 3: 组件迁移

- 实现 `useSessionStream` hook
- App.tsx 逐块切换：消息渲染 → pipeline 渲染 → 报告渲染 → 输入提交 → 会话切换
- 每块切换后跑全量测试；删除清单逐项核销
- 产出：App.tsx ≤ 800 行；ref ≤ 5 个；删除清单清空

### Phase 4: 守卫测试核销与收尾

- 逐一评估 10 个 guard 测试：守护的问题在结构上已不可能的 → 删除；仍有价值的 → 改写为 store 级测试
- 更新 OpenSpec / ADR（新增 ADR：前端流状态所有权外置）
- 事故记录文档更新：本次根因与结构性修复

## Open Questions

- 微批 emit 的 batching 窗口策略（requestAnimationFrame vs 固定 tick）需在 Phase 2 实测后确定
- `appState` 中剩余的 UI 模式状态（如侧边栏开关）是否需要在本次一并收拢，或留待后续迭代
