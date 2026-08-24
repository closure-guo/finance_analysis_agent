# Design: add-report-export

## Approach

**PDF 引擎选 WeasyPrint**：报告以 Markdown 存储（含表格与 PNG 图表引用），WeasyPrint 走「Markdown → HTML → PDF」管线，中文（配合 Dockerfile 已装的 fonts-noto-cjk）、表格、页眉页脚、图片嵌入都原生支持，是投入产出比最高的服务端真实 PDF 方案。生成逻辑放 `export/pdf_exporter.py`，复用 `export/parser.py` 的 Markdown 结构解析。

**导出逻辑抽成可复用服务**：`export/service.py` 提供 `export_report(markdown, stock_code, stock_name, formats) -> file_paths`，统一追加免责声明、统一图片缺失容错（转换前检查 `![...](path)` 源文件存在性，缺失即跳过）。`nodes/output.py` 的 `generate_file`（管线结束自动生成 docx/pptx）改为调用该服务并扩展为四格式（`docx/pptx/pdf/md`），行为向后兼容——单格式失败置 `null` 不中断管线。

**按需导出接口**：`POST /api/export`，入参 `{session_id, fmt}`（fmt 枚举 `pdf|word|markdown`）。从 `session_store` 读该会话 `report_markdown` → 调 `export_report` 生成单文件到 `REPORTS_DIR` → 返回 `{file_name, url: /api/files/<name>}`。错误语义：会话不存在/无 report → 404；格式非法 → 400；转换异常 → 500（不残留半成品 URL）。`word` 映射到 docx、`markdown` 映射到 md，与 `file_paths` 的四键契约对齐。

**前端导出抽屉**：新增 `ReportFileDrawer` 组件（右侧滑出 Drawer，默认关闭）。两个打开入口：「全部文件」横幅（报告卡片头部）与文件「预览」按钮。抽屉内三态：文件列表（依据 `filePaths` 四键渲染格式徽标行）→ 预览面板（复用 `react-markdown` 渲染正文，仅关闭抽屉的图片忽略规则延续）→ 格式下载（已有文件直接 `/api/files/...` 下载；缺失则先 `POST /api/export` 现场生成再下载）。关闭：右上角 X / 遮罩点击 / Esc。`ReportCard` 中现存的 Word/PPT 硬编码链接删除，替换为「全部文件」横幅。

**依赖与部署**：`requirements.txt` 增 `weasyprint`；Dockerfile apt 增 `libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 shared-mime-info`（WeasyPrint 系统库）。注：Windows 本地直接跑后端需额外安装 GTK 运行时，属已知环境摩擦，生产以 Docker 为准。

## Alternatives Considered

- **fpdf2（纯 Python，无系统依赖）**：胜在跨平台零依赖，但中文需手动注册 TTF、表格与图片要手动排版，渲染质量显著低于 WeasyPrint，工作量更大。仅在「Windows 本地直跑是常态」时才值得，本项目以 Docker 部署为主，不选。
- **ReportLab（纯 Python，底层）**：排版可控性最强，但需手写整页布局，从 Markdown 出 PDF 投入最大，对结构化报告属于过度设计。不选。
- **浏览器打印导出（方案 B）**：零后端改动，但依赖浏览器排版、需用户在打印弹窗操作，且无法从历史会话按需重建。用户已明确选服务端生成（方案 A），不选。
- **assistant-ui**：经调研（`AttachmentPrimitive` 仅渲染聊天附件占位缩略图，无文件列表/预览/下载/导出），其组件面向 chat 场景，无本功能所需能力，不引入。

## Risks

- **风险 1：历史会话图表 PNG 已清理**（`report_markdown` 引用临时目录路径）→ 导出服务做图片存在性检查并跳过缺失图片，PDF/Word 优雅降级；本 delta 不承诺历史图片可恢复。
- **风险 2：WeasyPrint 系统依赖**（Windows 本地开发需 GTK）→ 生产走 Docker（apt 安装系统库）；文档标注本地直跑注意事项。
- **风险 3：`file_paths` 契约扩展影响旧前端** → 键新增为可选（值为 `null` 表示不可用），旧逻辑按 key 存在性判断，向后兼容。
- **风险 4：并发导出同名文件** → 文件命名沿用现有 `{stock_code}_{timestamp}` 模式，`timestamp` 含秒级时间戳，冲突概率可忽略。