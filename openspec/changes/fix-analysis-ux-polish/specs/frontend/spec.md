# frontend delta: fix-analysis-ux-polish

## MODIFIED Requirements

### Requirement: 管线「已用时」计时源为后端启动时间

刷新重建 running 管线时，「已用时」SHALL 以快照 `pipeline_start_ts` 为计时起点；快照缺该字段时 SHALL 回退为前端本地时间（向后兼容）。

#### Scenario: 快照含启动时间戳时用其计时

- GIVEN 后端快照含 `pipeline_start_ts`
- WHEN `selectSession` 重建 running 管线消息
- THEN `msg.startedAt` SHALL 取 `pipeline_start_ts` 而非 `Date.now()`

#### Scenario: 快照缺启动时间戳时回退本地

- GIVEN 后端快照不含 `pipeline_start_ts`（旧数据/未升级后端）
- WHEN `selectSession` 重建 running 管线消息
- THEN `msg.startedAt` SHALL 回退为本地时间，不报错

### Requirement: 会话运行中（含工具执行中）禁止发送

会话处于运行中（含澄清阶段工具执行中）时，前端 SHALL 拦截发送并提示；追问路径（后端不重发 `session_created`）下拦截同样生效。

#### Scenario: 澄清工具执行中发送被拦截

- GIVEN 某会话澄清阶段 agent 正在执行工具（SSE 流存活）
- WHEN 用户在该会话输入框发送消息
- THEN 前端 SHALL 判定 `isSessionRunning(sessionId)` 为 true
- AND 拦截发送并显示「该会话正在生成中」提示
- AND 不发出新的分析/对话请求

#### Scenario: 追问路径登记 abort 使拦截生效

- GIVEN 一次追问（已有 sessionId，后端不重发 `session_created`）
- WHEN 前端发起 SSE 请求并创建 `localAbort`
- THEN 前端 SHALL 在 fetch 发出前将 `localAbort` 登记进 `streamRegistry.get(sessionId).abort`

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
