# ADR-0012: Session Management, Streaming, and Natural Language Input

**Status**: Accepted  
**Date**: 2026-07-05

## Context

v1.0 的前端是单页面、无状态、纯代码输入的交互模式：用户输入股票代码 → 等 2-3 分钟 → 一次性看到报告。刷新即丢失，无法回看历史，无法追问，无法输入股票名称。

参考 Kimi Agent 的交互模式（左侧时间轴侧边栏、逐 Token 流式、72h 中断恢复、自然语言输入），需要为 v1.1 实现四个能力：

1. **历史记录** — 侧边栏展示过往分析，点击切换
2. **多会话管理** — 新建/切换/搜索/重命名/删除
3. **自然语言交互** — 输入"宁德时代"而非"300750"
4. **流式输出** — 报告逐 Token 渐进渲染

## Decision

### D1: Session 定义 = 一次股票深度分析 + 后续追问

一个 Session = 一次 5 层 pipeline 分析 + 报告 + 后续追问链。不支持在同一会话内分析多只股票，不支持多会话并行（一次只跑一个 pipeline）。

### D2: 后端 SQLite 永久存储

会话存 SQLite（落实 ADR-0004 规划的 `report_snapshots` 表），永久保留直到用户手动删除。每个会话存储：

| 字段 | 内容 |
|------|------|
| session_id | UUID |
| stock_code / stock_name | 股票代码/名称 |
| created_at / duration | 创建时间/耗时 |
| report_markdown | 最终报告 Markdown |
| chart_data | 结构化图表数据 JSON |
| analyst_reports | 4 份 AnalystReport 完整 JSON |
| agent_process | Layer II-V 中间输出 JSON（辩论/决策/风控/基金经理） |
| analyst_summaries | 4 个分析师 summary 字段（用于追问上下文） |
| chat_history | 追问对话历史 |

### D3: 自然语言解析 = LLM 优先 + AKShare 兜底

用户输入任意文本 → 后端先调 LLM 解析为股票代码（LLM 认识大部分 A 股）→ LLM 返回 null 时 fallback 到 `ak.stock_info_a_code_name` 模糊匹配（已有 `app_search.py` 基础设施）→ 仍无结果返回错误提示。

### D4: 逐 Token 流式输出

报告生成和追问回复均逐 Token 通过 SSE 推送。后端 LLM 调用开启 `stream=True`，每个 token 通过 SSE 事件推送。前端用 Fetch Stream（非 EventSource，因需 POST）逐 chunk 读取，渐进渲染 Markdown。流式过程中渲染纯文本 + 基础格式，完成后完整解析 Markdown。

### D5: 中断恢复 = 后台异步执行

pipeline 与 HTTP 请求解耦：`graph.invoke()` 放后台任务执行，SSE 连接只负责推送进度。浏览器关闭后 pipeline 继续跑完，结果存 SQLite。用户重新打开 → 侧边栏看到会话状态"已完成" → 点击查看报告。不接入 LangGraph checkpoint（ADR-0004 提到 SqliteSaver 未接入），不做到 Layer 级断点恢复。

### D6: 追问上下文 = 报告 + 分析师 summary

切回历史会话后可继续追问。上下文 = 报告 Markdown（~3000 tokens）+ 4 个分析师 summary（~500 tokens）。不注入完整 AnalystReport JSON（太大、结构化 JSON 注入效果差）。`AnalystReport.summary` 字段已存在（prompt 要求"一句话总结"），无需新增字段。

### D7: 侧边栏 = 新建/切换/删除/搜索/重命名

左侧边栏时间轴排列会话列表。支持：新建（「+」按钮）、切换（点击列表项）、删除（hover 删除图标）、搜索（按股票名称/代码过滤）、重命名（双击会话名）。默认会话名 = "{股票名称} {MM-DD HH:mm}"。

## Consequences

### 正面

- 用户可回看历史分析，不丢失工作成果
- 自然语言输入降低使用门槛
- 逐 Token 流式大幅改善等待体验（首字 < 2s）
- 中断恢复让用户不怕关闭浏览器
- 追问可基于历史上下文，回答更精准

### 负面

- 后端需新增 SQLite sessions 表 + CRUD API（~5 个端点）
- pipeline 需与 HTTP 请求解耦（`BackgroundTasks` 或 `asyncio.create_task`）
- 前端需新增侧边栏组件 + Fetch Stream 读取逻辑 + 会话状态管理
- 追问上下文 ~3500 tokens/次，多次追问 token 消耗累积
- 流式 Markdown 渲染有不完整代码块/表格暂时破坏渲染的问题

### 风险

- DeepSeek API 并发流式调用可能有 rate limit（追问流式 + pipeline 内部 LLM 调用）
- SQLite 单文件并发写入（后台 pipeline 写 + 用户追问读）需加锁或 WAL 模式
- `AnalystReport.summary` 质量取决于 prompt，若 LLM 生成的 summary 过长需截断

## Alternatives Considered

| 方案 | 否决理由 |
|------|---------|
| localStorage 存历史 | 5-10MB 上限，~50 个会话即超限；不跨设备 |
| 逐章节分块流式 | 不是逐字效果，体感不如逐 Token |
| LangGraph checkpoint 断点恢复 | SqliteSaver 未接入，改造成本高 |
| 追问注入完整 AnalystReport JSON | ~20KB JSON 注入 system prompt 效果差，token 浪费 |
| 多会话并行 | DeepSeek API 并发限制 + AKShare 反爬 + 前端状态复杂 |
| 前端本地股票字典 | 200KB 打包体积，需定期更新 |
