# Design: update-file-export-entry

## Context

当前文件导出入口只有一处：报告卡标题区的「全部文件」按钮（`open-files-banner`，`App.tsx` ReportCard 头部），点击后由 `setDrawerMessage(msg)` 打开右侧 `ReportFileDrawer` 抽屉（`drawerMessage: UIMessage | null` 状态驱动，`currentSessionId` 变化时自动关闭）。抽屉当前按 `EXPORT_FORMATS`（pdf/docx/markdown）渲染格式行，缺失格式点击后走 `POST /api/export` 现场生成。

本次变更将导出入口改为会话级三入口（报告名横幅 + 全部文件横幅 + 全局顶部栏按钮），移除报告标题区入口，并将抽屉列表改为「自上而下仅列已生成的可下载文件」。`add-report-export` 的 delta 尚未 sync 主库，但其代码（抽屉）已在位，本设计直接复用。

## Goals / Non-Goals

**Goals:**
- 报告卡头部不再承载导出入口，头部标题改为「股票名称（股票代码）」
- 会话存在可导出报告（已完成且 filePaths 含至少一个已生成文件）时：报告产出轮次底部显示「报告名横幅」（标题=「股票名称（股票代码）」，位次先于全部文件横幅），对话尾部显示「全部文件」横幅，顶部栏显示「查看全部文件」按钮
- 报告消息同时携带股票名称与代码（`report_ready` 增发 `stock_code`），报告卡头部标题与报告名横幅据此组合展示名称与代码；历史会话恢复用会话元数据兜底
- 右侧抽屉自上而下仅列出已生成的可下载文件（`filePaths` 条目），不再展示 pdf/docx/markdown 三格式矩阵，无现场生成入口
- 导出报告文件名加入股票名称
- 抽屉预览、关闭行为保持不变

**Non-Goals:**
- 不改后端导出接口契约（`/api/files`、`/api/export`）
- 不做多报告会话的逐报告「全部文件」横幅（全部文件横幅为会话级单一入口；报告名横幅逐报告出现）
- 不保留抽屉内的按需生成（缺失格式不再有按钮，属本次明确取舍）

## Decisions

### D1: 会话级「可导出报告」的派生方式

从当前会话 `messages` 派生：取已完成且 filePaths 含至少一个已生成文件的报告消息（`type='report'`、`streaming=false`、`filePaths` 非空）作为「可导出报告」；入口可见性 = 存在这样的报告消息；点击入口 = `setDrawerMessage(对应报告消息)`。复用现有 `drawerMessage` 状态机，无需新状态。报告消息须含 `stockName`（股票名称或回退代码）与 `stockCode`（股票代码），供报告名横幅与报告卡头部组合标题。

- 备选 A：为每个报告消息在各轮次独立生成「全部文件」横幅 → 会话级入口语义被破坏。
- 备选 B：后端新增「会话可导出状态」接口 → 前端已持有消息数据，无需额外请求。

### D2: 对话区双横幅的组成与位次

- 「报告名横幅」：随报告消息渲染，紧跟该报告产出轮次的最后一条消息（报告消息及其后的「分析完成」系统消息）之后；标题取「股票名称（股票代码）」（如「贵州茅台（600519）」），当 `stockName` 为空或等于 `stockCode` 时只显示代码（不重复组合）；点击 `setDrawerMessage(该报告消息)`。仅报告消息（streaming=false 且 filePaths 非空）触发，快速对话/澄清轮次不渲染。
- 「全部文件横幅」：渲染在消息列表容器（`App.tsx` 中 `max-w-3xl` 的 messages 容器）内最后一条消息之后；点击 `setDrawerMessage(最后一条可导出报告)`。
- 位次约束：报告名横幅挂在其报告轮次之后，全部文件横幅挂在会话末尾 → 后者天然出现在所有报告名横幅之下/之后，满足「位次先于全部文件」。
- 两者各自新增 `data-testid`（如 `report-banner-<msgId>` / `conversation-files-banner`）供 E2E 稳定选择。

### D2.1: 股票名称与代码的数据链路

当前 `report_ready` 仅下发 `stock_name`（`api.py` 在名称未解析时回退为代码，`api.py:826/986`），报告消息不含代码字段。为支撑「名称（代码）」组合标题：后端 `report_ready` 载荷增发 `stock_code`（`stock_code` 参数本就存在，仅新增字段，非破坏）；前端 `UIMessage` 增加 `stockCode?: string`，`report_ready` 处理（`reduce.ts`）将 `event.stock_code` 与 `event.stock_name` 一并落库。报告卡头部标题（h3）与报告名横幅统一使用「股票名称（股票代码）」组合与回退规则（名称缺失或等于代码时仅显示代码）。历史会话恢复路径（chat_history）恢复的报告消息无 `stockCode` 时，由会话元数据（`stock_code`）兜底组合；会话元数据亦缺失时仅显示 `stockName`。

### D2.2: 会话持久化报告文件产物（file_paths）

sessions 表当前无 `file_paths` 列，`GET /api/sessions/{id}` 不返回文件产物；恢复路径（`streamStore/index.ts` 重建 reportMsg）因此拿不到 `filePaths`。按「已生成文件」口径 B，刷新后恢复的会话将看不到任何导出入口——回归。方案：sessions 表按既有迁移模式（`session_store.py` 的 ADD COLUMN 列表）新增 `file_paths TEXT`；报告完成时 `update_session_report` 落 `file_paths`（JSON 序列化，缺省 `{}`）；`get_session` 按 `chart_data` 同款 JSON 解析模式反序列化；`SessionDetail` 增加 `file_paths` 字段，前端恢复 reportMsg 时映射 `filePaths`。向后兼容：旧会话无列/为 NULL → 空 dict，横幅不显示，不报错。

### D5.1: 导出报告文件名（后端）

自动生成文件的 `base_name`（`export/service.py:69`）由 `{stock_code}_{date}_report` 改为 `{stock_name}_{stock_code}_{date}_report`（`stock_name` 为空时回退仅代码；`service.export_report` 的 `stock_name` 参数已存在，改动为单点）。文件扩展名与各格式转换逻辑不变；`/api/files/<basename>` 下载路径、抽屉展示的 basename 随之一致变化。

### D3: 全局顶部栏按钮

渲染在固定顶部栏 `<header>`（空状态首页不渲染 header，天然隐藏）右侧控件组「设置」按钮旁；可见性同 D1（存在可导出报告）；点击 `setDrawerMessage(最后一条可导出报告)`。新增 `data-testid`（如 `topbar-files-button`）。

### D4: 移除报告标题区入口

删除 ReportCard 头部的 `open-files-banner` 按钮；`ReportCard` 与 `MessageRenderer` 不再接收/传递 `onOpenFiles` prop。抽屉改由 D2/D3 三处入口驱动，`drawerMessage` 状态与 `currentSessionId` 切换自动关闭逻辑保持不变。

### D5: 抽屉文件列表改造

`ReportFileDrawer` 不再遍历 `EXPORT_FORMATS` 渲染格式行，改为遍历 `drawerMessage.filePaths` 的全部条目：每项显示文件 basename 与下载动作（`/api/files/<basename>`），图标按扩展名映射（pdf/docx/md/pptx 各自 fa- 图标）；自上而下排列。移除「缺失格式 → POST /api/export 现场生成」按钮分支；`filePaths` 为空时显示「暂无已生成文件」空态，预览视图（reportMarkdown）与关闭交互保持不变。

- 备选：保留格式行但隐藏缺失项 → 仍会展示「PDF / Word / Markdown」三格式结构，与「不再展示三种格式」要求冲突，不取。

## Risks / Trade-offs

- [依赖 add-report-export 抽屉能力] 其 delta 未 sync 主库，但代码已在位 → 实施前提：确认 `ReportFileDrawer` 可用；主库 sync 顺序并行冲突按 `project-workflow.md` §6 后到者 rebase 规则处理
- [report_ready 载荷扩充] 增发 `stock_code` 字段为非破坏性新增；SSE 事件契约由 frontend spec 的 Report Streaming Render 需求承载，需同步 MODIFIED + 后端事件测试；e2e LLM stub / fixtures / seed 与 `TESTING=1` 驱动的 stub 套件需同步载荷字段，否则 E2E 门禁变红
- [导出文件命名变更] 文件名含名称后，旧报告文件（无名称前缀）不受影响（历史文件路径已入库）；新增文件命名规则前后保持「文件名唯一性」（stock_code + 时间戳仍唯一）
- [股票名称解析失败] 名称缺失时报告名横幅/报告卡头部回退仅显示代码 → spec 已定义回退规则，不重复组合
- [移除现场生成入口] 缺失格式不再可从抽屉按需生成，功能缩水 → 属本次需求明确取舍；后端 `/api/export` 保留，未来可加回
- [多报告会话] 报告名横幅逐报告出现、全部文件横幅取最后一条报告 → 当前业务一个会话一条报告，复杂度可控
- [E2E 选择器稳定性] 新入口依赖真实 DOM → 实施时用 playwright-test-generator 探真实快照取 `data-testid`，禁止盲写

## Open Questions

- 无（「顶部横幅」指代已与用户确认：全局顶部栏）