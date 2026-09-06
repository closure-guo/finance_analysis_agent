# ADR-0019: 前端流状态所有权外置 StreamStore（reduce 纯函数 + 单读取器）

**Status**: Accepted  
**Date**: 2026-09-06  
**关联 delta**: refactor-frontend-stream-store；根因链见 docs/incidents/013、024

## Context

incident 013（流式输出概率性文字错乱）暴露的结构性问题：SSE 流状态的所有权散落在 3600 行的 `App.tsx` 主组件里——19 个 ref（streamRegistryRef、messagesRef、assistantMsgIdRef 37 处写入）、3 个手写 SSE reader 循环、多个并发入口（submit/resume/rebuild/switch）。状态转移逻辑（24 种 SSE 事件的收敛规则）与 React 渲染生命周期、副作用交织，竞态组合无法静态穷举：

- seq 去重依赖 ref 的同步时点，React 批处理推迟 ref 同步 → 并发双会话下丢 token 窗口被拉长；
- 3 个 reader 循环各自管理 abort，跨会话切换时旧 reader 退出与新 reader 建立之间存在重叠窗口；
- 每类并发 bug 的修复都是「加一个 ref / 加一个守卫」，守卫间相互作用又制造新 bug（fix-stream-event-routing、followup-sse-dedup 等连续补丁即证据）。

## Decision

将流状态所有权整体外置为模块级 `StreamStore`（`frontend/src/stores/streamStore/`），React 组件降级为纯订阅方：

1. **状态转移收敛为 reduce 纯函数**（`reduce.ts`）：24 种 SSE 事件的收敛规则无副作用、可独立单测（reduce.test.ts 38 用例，含全部事件类型与交错序列 fixture）。
2. **连接层单读取器不变量**（`index.ts`）：同会话任意时刻至多一个活跃 reader（submit/resume/switchSession/cancel 四入口统一收口，旧 reader abort 并等待退出后才建立新读取）；seq 守门（去重 + 空洞检测）内聚在 `applyEvent`。
3. **React 侧仅经 `useSessionStream`（useSyncExternalStore）订阅**：快照引用稳定（IDLE_STATE 常量），组件不持有流状态 ref；App.tsx 主组件逻辑从 ~1600 行降至 ~490 行，useRef 从 19+ 降至 4 个（UI 局部状态）。
4. **守卫测试语义迁移**：原挂在 App 集成层的竞态守卫测试（select-session-stale-guard、single-reader-invariant、session-created-ref-sync 等）全部改写为 store 行为测试，保护被删 ref 曾守护的不变量。

**备选否决**：
- 继续「补守卫/ref」路线——incident 013 已证明静态推理无法穷举竞态组合，边际收益为负；
- 迁移 React Query/Zustand 等通用状态库——SSE 流的读取器生命周期（abort/续传/单飞）是领域特有不变量，通用库不提供；
- Web Worker 隔离——postMessage 序列化开销与调试成本高，且不解决状态转移逻辑不可测的根本问题。

## Consequences

- 正面：竞态面从「19 ref × 3 reader × 多入口」收敛为「单读取器 + 纯函数」；行为回归可用纯函数级测试确定性断言（不再依赖概率性复现）；后补事件类型只需改 reduce 一处。
- 代价：store 与 App 间有一次性的迁移成本（已完成）；新增事件需同时维护 reduce 分支与类型（契约清晰，成本低）。
- 边界：store 只管流状态所有权，不管理 UI 瞬态（弹窗/主题等仍归组件）；双后端多 worker 场景下 seq 连续性仍依赖后端单 worker 约束（AGENTS.md 红线）。

## References

- delta：refactor-frontend-stream-store（specs/frontend delta：流状态所有权与 reduce 契约）
- 根因链：docs/incidents/013（seq 竞态）→ docs/incidents/024（结构性修复）
- 实现：`frontend/src/stores/streamStore/{types,reduce,index,useSessionStream}.ts`
