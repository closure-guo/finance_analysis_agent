# Tasks: update-file-export-entry

## 1. 股票名称/代码数据链路与导出命名

- [x] 1.1 后端 `report_ready` 事件载荷增发 `stock_code` 字段（`src/finance_agent/api.py`），SSE 事件契约测试同步断言新字段
- [x] 1.2 前端 `UIMessage` 增加 `stockCode?: string`（`types.ts`），`report_ready` 处理（`reduce.ts`）将 `event.stock_code` 与 `stock_name` 一并落库
- [x] 1.3 后端导出文件名加入股票名称（`export/service.py` 的 `base_name` 改为「{名称}_{代码}_{日期}_report」），文件名含名称断言测试；历史文件路径不受影响
- [x] 1.4 会话持久化报告文件产物：sessions 表新增 `file_paths` 列（既有迁移模式），报告完成时 `update_session_report` 落库，`GET /api/sessions/{id}` 返回该字段；旧会话空值兼容
- [x] 1.5 前端恢复路径还原 `filePaths`：`SessionDetail.file_paths` + `streamStore/index.ts` 重建 reportMsg 映射；`ReportReadyEvent` 增补 `stock_code` 字段类型
- [x] 1.6 e2e LLM stub / fixtures（含 `TESTING=1` stub 套件与 seed）同步 `report_ready` 载荷的 `stock_code` 字段（经真实发射通路验证：stub 仅接管外部 LLM，report_ready 由真实 emission 路径带出 stock_code/file_paths，E2E 全绿，无需代码改动）

## 2. 拆除报告标题区导出入口

- [x] 2.1 移除 ReportCard 头部「全部文件」按钮（`open-files-banner`），报告头部不再渲染任何导出入口
- [x] 2.2 移除 `ReportCard` / `MessageRenderer` 的 `onOpenFiles` prop 传递（抽屉由新三入口驱动）
- [x] 2.3 报告卡头部标题（h3）改为「股票名称（股票代码）」展示（名称缺失或等于代码时仅显示代码）

## 3. 会话级三入口实现

- [x] 3.1 实现「可导出报告」派生：从当前会话 messages 取 `type='report'`、`streaming=false`、`filePaths` 非空的报告消息
- [x] 3.2 报告名横幅：每条可导出报告在其产出轮次底部（紧随报告消息及「分析完成」系统消息）渲染，标题=「股票名称（股票代码）」、名称缺失或等于代码时仅显示代码、历史恢复无 stockCode 时用会话元数据兜底，位次先于「全部文件」横幅，点击 `setDrawerMessage(该报告)`
- [x] 3.3 全部文件横幅：会话存在可导出报告时渲染在消息列表最后一条之后，点击 `setDrawerMessage(最后一条可导出报告)`，无可导出报告时不渲染
- [x] 3.4 全局顶部栏「查看全部文件」按钮：存在可导出报告时显示于设置按钮旁，点击打开同一抽屉，无可导出报告/空状态时隐藏

## 4. 抽屉文件列表改造

- [x] 4.1 `ReportFileDrawer` 列表改为自上而下遍历 `filePaths` 渲染可下载文件条目（图标按扩展名、文件名、下载动作），移除 pdf/docx/markdown 三格式行
- [x] 4.2 移除缺失格式的现场生成按钮分支（不再 `POST /api/export`）；`filePaths` 为空时显示「暂无已生成文件」空态
- [x] 4.3 抽屉预览（reportMarkdown）、关闭（X/遮罩/Esc）行为保持不变

## 5. 测试与验证

- [x] 5.1 前端单测（先红后绿）：报告头部无导出按钮且标题为「名称（代码）」；报告名横幅（含标题与回退规则、历史会话元数据兜底）/全部文件横幅的条件渲染与位次；顶部栏按钮条件渲染；横幅/按钮点击打开抽屉；抽屉文件列表仅含已有 filePaths 条目；报告消息含 stockCode；会话切换后入口刷新
- [x] 5.2 E2E spec 已覆盖核心交互场景（交互类变更）：有报告会话显示报告名横幅与全部文件横幅并可打开文件列表、无报告会话不显示、顶部栏按钮、切换会话后刷新
- [x] 5.3 后端测试回归通过（`uv run pytest`）+ lint/类型检查通过（`uv run ruff check` / `uv run mypy`）
- [x] 5.4 E2E 门禁通过（`cd e2e && npx playwright test`，stub 套件全绿）
- [x] 5.5 人工验证：`tests/validation/YYYY-MM-DD-update-file-export-entry-validation.md` 已落库（抽查双横幅/顶部按钮/抽屉列表与主观体验）