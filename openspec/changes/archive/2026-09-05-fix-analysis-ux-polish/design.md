# Design: fix-analysis-ux-polish

四个独立 UI/交互缺陷的点修复，根因均已调查定位（见 proposal）。无新架构，仅最小改动。

## 1. 已用时后端计时

- **现状**：前端 `msg.startedAt = Date.now()`（本地），刷新丢失。
- **方案**：后端 `_persist_snapshot`（agent_factory.py:332）快照 dict 增 `pipeline_start_ts`，取已有 `_pipeline_start_time`（agent_factory.py:316，管线启动时刻，秒）×1000。前端 `selectSession` 重建 running 管线（App.tsx:428）`startedAt` 优先 `snapshot.pipeline_start_ts`，缺省回退 `Date.now()`。
- **兼容**：旧快照无该字段 → 前端回退本地，不报错。

## 2. 工具执行中禁止输入

- **根因**：追问路径后端不重发 `session_created`（api.py:1171），前端 `localAbort` 唯一登记点是 `session_created`（App.tsx:813），追问永不到达 → `streamRegistry` 无 abort → `isSessionRunning` false → 拦截旁路。
- **方案**：在 `startAnalysis`（App.tsx:742 `if (sessionId)` 补丁处）与 `quickChat`（约 1951 同构补丁处），fetch 发出前补 `getStreamState(sessionId).abort = localAbort`。终态 `handleStreamTerminal` 置 null 天然兼容。
- **不动**：isSessionRunning 判定逻辑、streamRegistry 机制本身。

## 3. warning 顶部 toast

- **现状**：warningMessage 渲染在「停止按钮容器」内（App.tsx:2210-2218），容器 `fixed bottom:90px z-40`，与输入框（z-40）同级且后渲染被压。
- **方案**：拆出为独立 fixed 顶部 toast：`fixed top-16 z-[60] left-1/2 -translate-x-1/2`，3s 自动消失（现有 setTimeout 不变）。移除原容器对 warningMessage 的条件耦合（2205 行 `|| warningMessage` 与 2210-2218 内嵌渲染）。

## 4. 澄清回复格式

- **现状**：实时流式渲染丢单 `\n`、列表粘连；落库文本正确，刷新重建正常。端到端 chat_token 路径测试正常 → 疑走 thinking 流/DSML 剥离路径。
- **方案**：先补复现测试（模拟 thinking 流路径），定位丢 `\n` 环节，再修。具体修复点待复现后确定。
