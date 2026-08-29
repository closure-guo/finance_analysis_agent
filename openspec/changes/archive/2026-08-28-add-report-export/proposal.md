# Proposal: add-report-export

## Why

当前报告导出能力有两个缺口：一是只有 Word/PPT 两种格式，且**仅依赖管线结束时的自动生成文件**——历史会话无法再导出，文件被清理后就彻底丢失；二是前端只有两个硬编码下载链接，交互原始，没有「先预览确认、再选格式下载」的闭环。

用户希望像 Kimi 等 AI 应用那样：分析完成后，通过一个**可开可关的右侧文件抽屉（默认关闭）**，对**当前或任意历史会话**按需导出 **PDF / Word / Markdown** 三种格式，每次导出一个文件，先预览再下载。

## What Changes

- 后端新增**按需导出接口** `POST /api/export`：入参 `{session_id, fmt}`（fmt ∈ `pdf` / `word` / `markdown`），从会话读取 `report_markdown` 现场生成**单一文件**，返回可下载 URL
- 新增 **PDF 导出器**（WeasyPrint：Markdown → HTML → PDF，支持中文、表格、页眉页脚与 PNG 图表嵌入）
- 抽取**可复用导出服务**：`generate_file`（管线结束自动生成）与按需导出共用同一套 Markdown→文件 转换逻辑
- `file_paths` 契约扩展：`{docx, pptx}` 扩展为 `{docx, pptx, pdf, md}`，`report_ready` 事件照常携带
- 前端报告卡片：硬编码的 Word/PPT 导出按钮改为**「全部文件」入口横幅**，点击滑出右侧**文件导出抽屉**
- 新增右侧**导出抽屉**（默认关闭）：打开入口（「全部文件」横幅 / 文件「预览」按钮）、文件列表（格式徽标）、预览面板（Markdown 正文渲染）、按格式下载（每次一份；无现成文件时先调 `/api/export` 现场生成）

## Capabilities

### New Capabilities

- `report-export`: 按需导出接口（任意会话、三种格式、单文件）、服务端 PDF 生成、`file_paths` 扩展契约

### Modified Capabilities

- `frontend`: 报告卡片的文件导出交互由硬编码 Word/PPT 链接改为「全部文件」横幅 + 可开可关的导出抽屉（列表 / 预览 / 格式选择下载）

## Impact

- **后端代码**：
  - [export/pdf_exporter.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/export/pdf_exporter.py)（新建）— `markdown_to_pdf`，WeasyPrint 渲染
  - [export/service.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/export/service.py)（新建）— `export_report` 可复用导出服务（docx/pptx/pdf/md + 免责声明 + 图片缺失容错）
  - [nodes/output.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/nodes/output.py) — `generate_file` 改为调用导出服务，`file_paths` 增 `pdf`/`md`
  - [api.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/api.py) — 新增 `POST /api/export`；`report_ready` 携带扩展后的 `file_paths`
- **前端代码**：
  - [App.tsx](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/App.tsx) — ReportCard 的 Word/PPT 链接替换为「全部文件」横幅；新增导出抽屉
  - [types.ts](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/types.ts) — `file_paths` 类型对齐四格式
- **依赖**：`requirements.txt` 新增 `weasyprint`；Dockerfile apt 新增 `libpango` / `libcairo` / `libgdk-pixbuf` 系统库
- **API 契约**：新增 `POST /api/export`（请求 `{session_id, fmt}`，响应 `{file_name, url}`）；`GET /api/files/{filename}` 不变
- **测试**：后端单测（PDF 合法性 / 导出服务 / 接口错误码）+ E2E spec（抽屉开合、预览、格式下载）——交互类变更，适用 E2E 门禁