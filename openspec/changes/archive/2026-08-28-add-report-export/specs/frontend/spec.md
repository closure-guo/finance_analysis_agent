# Delta for Frontend

## MODIFIED Requirements

### Requirement: Report Card Rendering

系统 SHALL 在报告消息中渲染报告头部、文件导出入口、财务图表、Markdown 正文、参考资料和免责声明。
(Previously: 系统 SHALL 在报告消息中渲染报告头部、文件导出（Word/PPT 硬编码下载按钮）、财务图表、Markdown 正文、参考资料和免责声明。)

#### Scenario: 流式报告显示生成指示器

- **GIVEN** 报告消息 streaming=true
- **THEN** 顶部显示"正在生成报告 · 流式输出中"指示器（脉冲动画）

#### Scenario: 报告头部展示

- **GIVEN** 报告消息 streaming=false
- **THEN** 显示股票名称（stockName）、"深度分析"标签、耗时信息
- **AND** 报告头部显示「全部文件」入口横幅（图标 + "全部文件"文案），点击可打开文件导出抽屉

#### Scenario: 打开导出抽屉

- **GIVEN** 报告头部已渲染，展示「全部文件」入口横幅
- **WHEN** 用户点击「全部文件」横幅
- **THEN** 右侧文件导出抽屉滑出打开
- **AND** 抽屉内列出该报告当前可用的导出文件（依据 filePaths 的 docx/pptx/pdf/md 键，带格式徽标与文件名）

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

## ADDED Requirements

### Requirement: 文件导出抽屉

系统 SHALL 提供可开可关的右侧文件导出抽屉（Drawer），默认关闭；仅当用户点击「全部文件」横幅或某文件的「预览」入口时打开。抽屉 SHALL 支持查看该会话的文件列表、预览报告 Markdown 内容、以及按格式下载**单一文件**（每次点击只下载一份）。

#### Scenario: 抽屉默认关闭

- **GIVEN** 报告卡片已渲染
- **WHEN** 页面加载且用户未点击任何导出入口
- **THEN** 右侧抽屉处于关闭状态，不遮挡主界面内容

#### Scenario: 预览入口打开并定位内容

- **GIVEN** 报告卡片或文件列表中存在某文件的「预览」按钮
- **WHEN** 用户点击「预览」
- **THEN** 抽屉滑出打开
- **AND** 抽屉显示该报告 Markdown 正文的预览面板（复用 react-markdown 渲染，图片标签忽略）

#### Scenario: 预览面板渲染报告正文

- **GIVEN** 抽屉处于打开状态且处于预览视图
- **THEN** 预览面板渲染报告的 Markdown 正文
- **AND** 预览区域可滚动查看完整内容

#### Scenario: 选择格式下载单一文件

- **GIVEN** 抽屉打开且文件列表已展示（docx/pptx/pdf/md 中至少一个可用）
- **WHEN** 用户点击某一格式的下载动作（如「PDF」）
- **THEN** 若该格式文件已存在（filePaths 有值），直接触发下载，URL 为 `/api/files/{filename}`
- **AND** 若该格式文件不存在（filePaths 对应键为 null/缺失），先调用 `POST /api/export`（`{session_id, fmt}`）现场生成
- **AND** 生成成功后触发该文件的下载
- **AND** 每次点击仅下载对应格式的**单一文件**，不打包多格式

#### Scenario: 关闭抽屉

- **GIVEN** 抽屉处于打开状态
- **WHEN** 用户点击关闭按钮（右上角 X）、点击遮罩、或按 Esc 键
- **THEN** 抽屉关闭，界面还原为默认无遮挡状态

#### Scenario: 无可用文件时展示空态

- **GIVEN** 报告消息无 filePaths（四格式均为空）
- **WHEN** 用户点击预览或进入抽屉
- **THEN** 预览面板仍可展示 Markdown 正文
- **AND** 文件列表显示空态提示（如"暂无已生成文件，可预览后按格式导出"），导出动作仍可用（走 `/api/export` 现场生成）