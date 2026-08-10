## Why

前端流状态（SSE 连接、事件缓冲、消息拼接、seq 游标、流归属）目前由 App 组件亲自持有，且同一事实存在三份拷贝（React state、ref 镜像、手写注册表）。三份拷贝靠 `commitMessages()` 手工同步，同步窗口即 bug 窗口。已修复大量 bug 后同族 bug 仍不断出现，说明架构在持续生产 bug，而非修复速度问题。

后端事件日志（`session_events` 表 + `GET /api/sessions/{id}/stream` 断点续传）已就绪，前端快照层已从"必要"变成"冗余且有害"。本次重构的本质是让前端快照层退役，唯一事实源收敛到后端事件日志。

## What Changes

- **新增 `StreamStore`**：React 之外的独立流状态管理器，作为唯一写入者和单一事实源
- **新增 `reduce` 纯函数**：`reduce(state, event)` 收拢全部状态迁移逻辑，可脱离 React 单测
- **组件只读订阅**：通过 `useSyncExternalStore` 订阅 store 快照，删除全部 ref 镜像与手工同步代码
- **会话切换/刷新恢复一律走后端 replay**：前端不再保存消息快照，切回时从后端重建 + `after_seq` 续传
- **单读取器结构性保证**：`pump` 开始前 abort 旧 reader，`single-reader-invariant` 从测试守护的约定变成结构保证
- **事件按 sessionId 分流写入**：迟到的事件写进它该去的会话，天然不会污染当前视图
- **seq 守门**：`applyEvent` 中去重过期事件，seq 空洞显式 resync 而非静默跳过
- **删除清单**：`streamRegistryRef`、`commitMessages`、`messagesRef` 等 19 个 ref 镜像、3 处手写 `getReader()` 循环、7 个手写守卫函数全部删除

## Capabilities

### New Capabilities

- `stream-store`: 前端流状态管理器（StreamStore），负责 SSE 连接生命周期、事件去重、状态迁移、会话切换协议

### Modified Capabilities

- `frontend`: 流状态所有权从 App 组件迁移到 StreamStore；组件从直接读写 state/ref 变为只读订阅；会话切换从命令式保存/恢复序列变为 store 内部原子协调；删除 ref 镜像、手工同步、手写守卫函数

## Impact

- **前端代码**：`frontend/src/App.tsx`（预计从 3518 行降至 ≤800 行）、新增 `frontend/src/stores/streamStore/` 目录（types.ts、reduce.ts、index.ts、useSessionStream.ts）
- **测试**：`frontend/src/test/` 下 10 个 guard 测试族处置（删除/改写为 store 级测试），新增 reduce 单测 + store 时序测试
- **后端**：无改动（事件日志与恢复端点已就绪）
- **OpenSpec**：`frontend/spec.md` 需更新（流状态管理相关需求行为描述变化）
- **文档**：新增 ADR（前端流状态所有权外置）、更新 `docs/incidents/` 事故记录
