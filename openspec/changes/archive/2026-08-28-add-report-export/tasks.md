# Tasks: add-report-export

- [x] `export/service.py` 可复用导出服务可用：`export_report` 支持 docx/pptx/pdf/md 四格式，统一免责声明，图片缺失优雅跳过
- [x] `export/pdf_exporter.py` 服务端 PDF 生成可用：含中文/表格/图片样例产出合法 `%PDF` 文件；图片缺失不失败
- [x] `POST /api/export` 按需导出可用：任一会话（含历史会话）可导出 pdf/word/markdown 单文件；会话不存在 404、格式非法 400、转换失败 500
- [x] `generate_file` 改为共用的导出服务，`file_paths` 含四键，单格式失败置 `null` 不阻断管线，`report_ready` 携带扩展契约
- [x] 前端报告卡片头部显示「全部文件」横幅，原 Word/PPT 硬编码按钮删除
- [x] 导出抽屉：默认关闭；「全部文件」横幅与「预览」按钮可打开；关闭按钮/遮罩/Esc 可关闭
- [x] 抽屉文件列表按 `filePaths` 渲染格式徽标；无文件时显示空态但可现场导出
- [x] 格式下载可用：已有文件直接下载；缺失文件先 `POST /api/export` 现场生成再下载；每次仅下载单一文件
- [x] 预览面板复用 react-markdown 渲染报告正文，可滚动
- [x] 后端单测覆盖：PDF 合法性、导出服务四格式、接口错误码（404/400/500）
- [x] E2E spec 已覆盖核心交互场景（抽屉开合、预览渲染、格式下载）
- [x] 人工验证报告已落 `tests/validation/`
- [x] 后端测试全绿（`uv run pytest`）+ Lint（`uv run ruff check`）+ 类型检查（`uv run mypy`，基线对比）+ E2E 门禁（`tests/e2e/playwright`）通过