# Design: restore-session-on-refresh

## Context

前端（`frontend/src/App.tsx`）的会话状态全部存于 React 内存。`currentSessionId` 是纯 `useState`（App.tsx:86），未持久化。刷新页面后 React 状态丢失，`appState` 回到 `'empty'`，渲染空状态首页。mount 时的初始化 effect 只调用 `loadSessions()` 拉取会话列表，**不会自动选中任何会话**。用户必须手动点击侧边栏中的会话，才触发 `selectSession(sessionId)` 恢复消息视图。

后端会话数据（chat_history 含 agentTimeline、pipeline_snapshot、pipeline_timelines、事件 journal）持久化完整，恢复数据源无缺失。问题仅在前端缺少「刷新后自动回到进行中会话」的入口。

现有恢复路径 `selectSession`（App.tsx:311 起）已完整覆盖：加载会话详情 → 从 chat_history 重建消息 → running 时经 resumeStream 重连 SSE。本设计复用该路径，不新增恢复通道。

## Goals / Non-Goals

**Goals:**
- 刷新后自动恢复此前正在查看的会话（进行中或已完成），无需手动点击。
- 复用现有 `selectSession` 恢复逻辑，行为与手动点击一致。
- 持久化会话已删除时优雅回退空态。

**Non-Goals:**
- 不改后端 API、事件 journal、chat_history 持久化。
- 不改手动切换会话行为。
- 不处理 10s 增量 upsert 窗口导致的重建粒度（由 SSE 实时事件追上覆盖）。
- 不引入 URL 路由（如 `/?session=<id>`）作为恢复载体（见 Decisions D2）。

## Decisions

### D1: 持久化载体用 localStorage，key 为 `fa_current_session_id`

与既有 `fa_user_id`、`fa_api_key` 同风格，读写简单，跨刷新保留。

- **备选**：sessionStorage——标签页关闭即失效，不能满足「关闭后重开」场景，排除。
- **备选**：URL query——需引入路由改造，且刷新/分享语义复杂，排除（见 D2）。

维护时机：在 `setCurrentSessionId` 的所有调用点同步写/清 localStorage——选中会话、session_created、删除当前会话、新建分析（置 null 时清除）。封装一个 `persistCurrentSession(id | null)` 辅助函数统一出入口，避免遗漏。

### D2: 恢复入口挂在「会话列表加载成功之后」

mount 初始化 effect 在 `loadSessions()` 首次成功后，读取 `fa_current_session_id`，若存在则调用恢复逻辑。挂在列表加载之后而非并行，原因：恢复前可校验该会话是否仍在列表中（存在性检查），已删除则清除 localStorage 并停留空态，避免对失效 id 发起无效请求。

- **备选**：mount 时直接 `selectSession(persistedId)`——无法先做存在性校验，会话已删时会发一次 404，再回退，多一次失败往返。

恢复逻辑复用 `selectSession`：直接调用它（传入持久化 id）。`selectSession` 内部已处理：会话不存在（get_session 返回空）时的兜底、chat_history 重建、running 时 resumeStream。需确认 `selectSession` 对「列表中不存在但 id 有效」也安全——存在性校验前置在 mount，正常情况 id 一定在列表中。

### D3: 防重复触发

自动恢复只应执行一次（mount 后首次列表加载成功时）。用一个 `restoredRef = useRef(false)` 标记，避免 `loadSessions` 后续被其他事件（session_created 等）触发时重复恢复、覆盖用户已切换的视图。

### D4: 与「无限重试加载列表」的衔接

承接上一变更（loadSessions 失败无限退避重试），自动恢复依赖列表加载成功。后端因分析阻塞暂未就绪时，列表加载会持续重试，成功后即触发自动恢复——刷新后即使后端短暂阻塞，恢复也会在后端就绪后自动完成，无需人工干预。

## Risks / Trade-offs

- [自动恢复覆盖了用户「回到首页」的意图] → 用户点「新建分析」会清除 `fa_current_session_id`，此时刷新回到空态，符合预期；只有「查看某会话中刷新」才自动恢复。
- [多标签页同时打开时 currentSessionId 互相覆盖] → localStorage 是单值，后写的标签页覆盖先写的。属于可接受的边缘场景（单用户本地工具），不引入 per-tab 状态。
- [恢复 running 会话时 SSE 重连失败] → 复用 selectSession/resumeStream 现有错误处理与防御性清理（spec: Streaming State Defensive Cleanup），不新增风险面。

## Migration Plan

纯前端改动，无后端迁移。localStorage 新增 key，旧版本无该 key 时走「无持久化会话保持空态」分支，向后兼容。回滚：移除自动恢复调用即可，持久化 key 残留无副作用。

## Open Questions

（无）
