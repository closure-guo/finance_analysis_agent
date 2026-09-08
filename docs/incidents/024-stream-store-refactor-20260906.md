# 024: App.tsx 流状态所有权分散 — StreamStore 结构性重构根治竞态土壤

**日期**: 2026-09-06  
**关联**: incident 013（seq 竞态根因）、delta `refactor-frontend-stream-store`、ADR-0019  
**状态**: 已修复（结构性）

## 现象

incident 013 修复（seq 竞态 CAS 作用域收窄）后，SSE 流相关补丁仍连续出现：fix-stream-event-routing、followup-sse-dedup、select-session-stale-guard、session-created-ref-sync……每个并发类 bug 的修复都是「再加一个 ref / 再加一个守卫」，守卫间的相互作用又制造新的时序问题。App.tsx 主组件累计 19 个流状态 ref、3 个手写 SSE reader 循环、1600+ 行。

## 根因

不是某个具体 bug，而是**架构性土壤**：流状态所有权分散在组件渲染生命周期里。

1. 24 种 SSE 事件的收敛规则以命令式 setState + ref 副作用散布，无法单测，只能靠「全量集成测试 + 概率性复现」兜底；
2. seq 去重的正确性依赖 ref 同步时点与 React 批处理的相对顺序——这是隐式契约，任何新入口都可能破坏；
3. 3 个 reader 循环各自管理 abort，单读取器保证靠人肉纪律维持（incident 013 的第四轮诊断已证明运行时轨迹是唯一可靠的排查手段）。

## 结构性修复

`refactor-frontend-stream-store` delta 落地 StreamStore（ADR-0019）：

- 状态转移收敛为 `reduce(state, event)` 纯函数（reduce.test.ts 38 用例，覆盖全部 24 类事件与交错序列）；
- 连接层单读取器不变量收口四入口（store.test.ts 23 用例：双会话独立、切换 abort、rebuild lastSeq、全量回放交错）；
- React 侧仅经 useSyncExternalStore 订阅，App.tsx 主组件 ~490 行、useRef 4 个；
- 原 App 集成层守卫测试全部改写为 store 行为测试（保护被删 ref 曾守护的不变量）。

验证：前端全量 490/490；E2E stub 门禁全绿；GUI 实测双会话并发 + 10 次快速切换内容自洽无串话、管线运行中取消即时终止（interrupted）、澄清→管线→报告完整链路（tests/validation/2026-09-06-refactor-frontend-stream-store-validation.md）。

## 防止再发

1. **新增 SSE 事件类型时只改 `reduce.ts` 一处**——禁止在组件里直接处理事件写状态；
2. **任何绕过 store 直连 SSE 的代码（新 reader 循环）视为架构回退**，评审必须打回；
3. 竞态类报告先看 store 单读取器不变量是否被破坏，再考虑新守卫。

## 遗留

- quick 通道（AG-UI runtime）不经 StreamStore，由 assistant-ui 状态管理（add-assistant-ui-thread 架构，双轨隔离是显式设计）；
- store 的 seq 连续性依赖后端单 worker 约束（AGENTS.md 红线），多 worker 化时需一并设计。
