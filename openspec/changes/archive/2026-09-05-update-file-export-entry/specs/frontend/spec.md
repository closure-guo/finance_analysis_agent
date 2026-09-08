# Delta for Frontend

## MODIFIED Requirements

### Requirement: Report Streaming Render

系统 SHALL 在深度分析管线完成后，通过 report_chunk 事件渐进渲染报告，最终由 report_ready 事件完成；报告消息 SHALL 同时记录股票名称与股票代码，供报告名等展示使用。
(Previously: 系统 SHALL 在深度分析管线完成后，通过 report_chunk 事件渐进渲染报告，最终由 report_ready 事件完成。报告消息仅记录 stockName，不含股票代码。)

#### Scenario: 报告流式分块累积

- **GIVEN** 管线 UI 已渲染
- **WHEN** 收到 report_chunk 事件
- **THEN** 若尚无报告消息，创建一条 streaming=true 的报告消息，初始内容为事件文本
- **AND** 若已有报告消息，将事件文本追加到 reportMarkdown
- **AND** 报告消息显示"正在生成报告"流式指示器

#### Scenario: 报告就绪完成渲染

- **GIVEN** 报告消息正在流式生成
- **WHEN** 收到 report_ready 事件
- **THEN** 更新报告消息：reportMarkdown 替换为最终完整版、chartData、filePaths、stockName、stockCode、durationMs、sessionId、webSources，streaming=false
- **AND** appState 切换为 'report'
- **AND** 设置 currentSessionId 为事件中的 session_id
- **AND** 刷新侧边栏会话列表
- **AND** 添加系统消息"分析完成 · 耗时 {N} 秒"

#### Scenario: 无流式分块直接就绪

- **GIVEN** 管线 UI 已渲染，尚未收到任何 report_chunk
- **WHEN** 直接收到 report_ready 事件
- **THEN** 创建一条完整的报告消息（streaming=false），包含所有最终数据（含 stockName 与 stockCode）

### Requirement: Report Card Rendering

系统 SHALL 在报告消息中渲染报告头部、财务图表、Markdown 正文、参考资料和免责声明；报告头部 SHALL NOT 承载任何文件导出按钮或「全部文件」入口。
(Previously: 系统 SHALL 在报告消息中渲染报告头部、文件导出、财务图表、Markdown 正文、参考资料和免责声明。报告头部显示「全部文件」入口横幅（图标 + "全部文件"文案），点击打开右侧文件导出抽屉，抽屉内依据 filePaths 的 docx/pptx/pdf/md 键列出导出文件。)

#### Scenario: 流式报告显示生成指示器

- **GIVEN** 报告消息 streaming=true
- **THEN** 顶部显示"正在生成报告 · 流式输出中"指示器（脉冲动画）

#### Scenario: 报告头部展示

- **GIVEN** 报告消息 streaming=false
- **THEN** 显示「股票名称（股票代码）」标题（如「贵州茅台（600519）」；名称缺失或等于代码时仅显示代码）、"深度分析"标签、耗时信息
- **AND** 报告头部不显示任何文件导出按钮或「全部文件」入口

#### Scenario: 打开导出抽屉

- **GIVEN** 任一会话级导出入口（报告名横幅 / 全部文件横幅 / 顶部栏「查看全部文件」按钮）已渲染（见「会话级文件导出入口」）
- **WHEN** 用户点击该入口
- **THEN** 右侧文件导出抽屉滑出打开
- **AND** 抽屉内仅列出该会话报告已生成的可下载文件（依据 filePaths 各条目，带格式徽标与文件名），不展示缺失格式的现场生成入口

#### Scenario: 财务图表展示

- **GIVEN** 报告消息包含 chartData 且 chartData.annual 非空
- **THEN** 在报告头部下方渲染 ChartsSection（ECharts 交互图表）

#### Scenario: Markdown 正文渲染

- **GIVEN** 报告消息包含 reportMarkdown
- **THEN** 使用 react-markdown + remark-gfm 渲染 Markdown
- **AND** 图片标签（img）被忽略不渲染
- **AND** 链接在新标签页打开
- **AND** 渲染区域最大高度 600px，可滚动

#### Scenario: 参考资料信源卡片

- **GIVEN** 报告消息 streaming=false 且包含 webSources（非空数组）
- **THEN** 在 Markdown 正文下方渲染信源卡片网格
- **AND** 每张卡片显示序号、标题、摘要、域名、favicon
- **AND** 标题显示"参考资料（N 个信源）"

#### Scenario: 免责声明

- **GIVEN** 报告消息 streaming=false
- **THEN** 在底部显示免责声明"本报告由 AI 系统基于公开数据自动生成，仅供参考研究，不构成投资建议。投资有风险，入市需谨慎。"

## ADDED Requirements

### Requirement: 会话级文件导出入口

系统 SHALL 在会话存在可导出报告（已完成 streaming=false 的报告消息且其 filePaths 含至少一个已生成文件）时，在对话区内渲染「报告名横幅」与「全部文件横幅」两个入口：报告名横幅位于产出该报告的对话轮次底部，位次先于「全部文件」横幅；「全部文件」横幅位于对话尾部（最后一条消息之后）。二者与全局顶部栏「查看全部文件」按钮均可打开右侧文件列表抽屉。抽屉 SHALL 自上而下仅列出该会话报告已生成的可下载文件（filePaths 各条目），不展示 pdf/docx/markdown 固定格式行，也不提供缺失格式的现场生成入口；预览与关闭行为沿用现有实现。

#### Scenario: 报告名横幅在报告产出轮次底部显示

- **GIVEN** 对话中存在一条已完成（streaming=false）且 filePaths 含至少一个已生成文件的报告消息
- **WHEN** 渲染对话消息列表
- **THEN** 在该报告产出轮次的底部（紧随该报告消息及其后的「分析完成」系统消息）渲染「报告名横幅」
- **AND** 横幅标题为该报告的「股票名称（股票代码）」（如「贵州茅台（600519）」）
- **AND** 该横幅位次先于「全部文件」横幅

#### Scenario: 股票名称缺失时报告名横幅回退显示

- **GIVEN** 报告消息 stockName 缺失或等于 stockCode（名称未解析到）
- **WHEN** 渲染报告名横幅
- **THEN** 横幅标题仅显示股票代码，不重复组合（不显示「600519（600519）」）

#### Scenario: 历史会话恢复后报告名横幅用会话元数据兜底

- **GIVEN** 从 chat_history / 会话详情恢复的报告消息无 stockCode 字段（旧会话）
- **WHEN** 渲染报告名横幅
- **THEN** 标题中的股票代码从会话元数据（stock_code）兜底获取
- **AND** 会话元数据亦缺失时，仅显示报告消息的 stockName
- **AND** 恢复的报告消息 SHALL 携带会话持久化的 filePaths（file_paths 非空时报告名横幅与全部文件横幅照常显示）

#### Scenario: 报告名横幅仅在报告产出轮次出现

- **GIVEN** 对话中某轮次未产出报告（澄清对话、快速对话、或分析进行中 streaming=true）
- **WHEN** 渲染对话消息列表
- **THEN** 该轮次底部不渲染报告名横幅
- **AND** 快速对话会话与空状态首页不渲染任何报告名横幅

#### Scenario: 全部文件横幅位于对话尾部

- **GIVEN** 当前会话存在可导出报告（已完成且 filePaths 含已生成文件）
- **WHEN** 渲染对话消息列表
- **THEN** 在最后一条消息之后渲染「全部文件」横幅
- **AND** 该横幅位次于所有报告名横幅之后

#### Scenario: 无可导出文件时不显示全部文件横幅

- **GIVEN** 当前会话无可导出报告（报告无已生成文件、空状态首页、快速对话会话、或深度分析进行中 streaming=true）
- **WHEN** 渲染对话消息列表
- **THEN** 对话尾部不显示「全部文件」横幅

#### Scenario: 点击报告名横幅打开该报告的文件列表

- **GIVEN** 报告名横幅已显示
- **WHEN** 用户点击该横幅
- **THEN** 右侧文件列表抽屉滑出打开
- **AND** 抽屉列出该报告消息 filePaths 对应的可下载文件

#### Scenario: 点击全部文件横幅打开右侧文件列表

- **GIVEN** 「全部文件」横幅已显示
- **WHEN** 用户点击该横幅
- **THEN** 右侧文件列表抽屉滑出打开

#### Scenario: 全局顶部栏按钮显示

- **GIVEN** 当前会话存在可导出报告（已完成且 filePaths 含已生成文件）
- **WHEN** 渲染全局顶部栏
- **THEN** 顶部栏右侧（设置按钮旁）显示「查看全部文件」按钮

#### Scenario: 无可导出文件时顶部栏按钮隐藏

- **GIVEN** 当前会话无可导出文件，或处于空状态首页（无 currentSessionId）
- **WHEN** 渲染全局顶部栏
- **THEN** 顶部栏不显示「查看全部文件」按钮

#### Scenario: 点击顶部栏按钮打开右侧文件列表

- **GIVEN** 全局顶部栏「查看全部文件」按钮已显示
- **WHEN** 用户点击该按钮
- **THEN** 右侧文件列表抽屉滑出打开

#### Scenario: 抽屉仅列出已生成的可下载文件

- **GIVEN** 抽屉已打开，报告消息 filePaths 含若干条目（如 docx/pdf 已生成，md 缺失）
- **WHEN** 渲染文件列表
- **THEN** 自上而下仅排列已存在的可下载文件条目（每项显示文件名与下载动作，图标按文件扩展名区分）
- **AND** 可下载文件名形如「{股票名称}_{股票代码}_{时间戳}_report.{扩展名}」（股票名称缺失时回退仅代码）
- **AND** 不显示 pdf/docx/markdown 固定三类格式行
- **AND** 不显示缺失格式的下载按钮（无现场生成入口）

#### Scenario: 无可下载文件时展示空态

- **GIVEN** 抽屉已打开，报告消息无 filePaths（或所有条目为空）
- **THEN** 文件列表显示空态提示（如「暂无已生成文件」）
- **AND** 预览功能仍可用

#### Scenario: 抽屉关闭与下载行为

- **GIVEN** 文件列表抽屉已由任一入口（报告名横幅 / 全部文件横幅 / 顶部栏按钮）打开
- **WHEN** 用户点击关闭按钮、点击遮罩、或按 Esc
- **THEN** 抽屉关闭
- **WHEN** 用户点击某文件的下载动作
- **THEN** 触发该文件下载，URL 为 /api/files/{basename}

#### Scenario: 会话切换后入口按新会话刷新

- **GIVEN** 用户从有可导出文件的会话切换到无可导出文件的会话（或反向）
- **WHEN** 渲染新会话的消息列表
- **THEN** 报告名横幅、全部文件横幅与顶部栏按钮按新会话的报告状态刷新显示或隐藏
- **AND** 若文件抽屉处于打开状态，随会话切换自动关闭（沿用现有行为）