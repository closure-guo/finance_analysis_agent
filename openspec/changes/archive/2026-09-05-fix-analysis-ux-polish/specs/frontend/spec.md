# frontend delta: fix-analysis-ux-polish

> Rebase 说明（2026-09-05）：原 delta 将 4 个需求标为 MODIFIED，但其目标需求从未进入主规范库
> （原链上的 Aug-5 时代 delta 未归档即被整理收编）。其中「管线『已用时』计时源为后端启动时间」
> 已被 enhance-pipeline-progress 归档进主规范的「节点已用时」需求覆盖（同语义），本 delta 不再重复；
> 其余 3 个需求主库无对应条目，按 ADDED 归档。

## ADDED Requirements

### Requirement: 会话运行中（含工具执行中）禁止发送

会话处于运行中（含澄清阶段工具执行中）时，前端 SHALL 拦截发送并提示；追问路径（后端不重发 `session_created`）下拦截同样生效。拦截主层为运行状态判定（运行中发送入口切换为停止按钮、提交通道关闭），App 层守卫（`isSessionRunning`）作为兜底。

#### Scenario: 澄清工具执行中发送被拦截

- GIVEN 某会话澄清阶段 agent 正在执行工具（SSE 流存活）
- WHEN 用户在该会话输入框发送消息
- THEN 前端 SHALL 判定 `isSessionRunning(sessionId)` 为 true
- AND 拦截发送并显示「该会话正在生成中」提示
- AND 不发出新的分析/对话请求

#### Scenario: 追问路径登记 abort 使拦截生效

- GIVEN 一次追问（已有 sessionId，后端不重发 `session_created`）
- WHEN 前端发起 SSE 请求并创建 `AbortController`
- THEN 前端 SHALL 在 fetch 发出前将其登记为该会话的活跃读取器（单读取器保证）
- AND 运行状态判定据此生效

### Requirement: 「会话生成中」警告为顶部 toast

「该会话正在生成中」警告 SHALL 以 fixed 顶部 toast 呈现（浮于 header 与输入框之上、水平居中），3 秒自动消失；不再锚定在底部停止按钮容器内。

#### Scenario: 警告置顶显示

- GIVEN 触发「该会话正在生成中」拦截
- WHEN 警告渲染
- THEN 其 SHALL 为 `position: fixed`、位于视口顶部、z-index 高于 header（z-50）与输入框（z-40）
- AND 3 秒后自动消失

### Requirement: 澄清回复实时流式与落库格式一致

澄清阶段回复的实时流式渲染 SHALL 保留落库文本的换行/列表结构，不丢失单 `\n`；刷新后重建显示与实时流式显示一致。

#### Scenario: 流式渲染保留列表换行

- GIVEN 澄清回复为多行 markdown 列表（每项独立一行，单 `\n` 分隔）
- WHEN 前端实时流式渲染该回复
- THEN 渲染结果 SHALL 与落库文本一致（列表项分行，不粘连）
- AND 刷新后重建显示与流式显示一致
