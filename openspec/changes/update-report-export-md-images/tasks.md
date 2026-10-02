## 1. 测试先行（TDD 红）

- [ ] 1.1 `tests/export/test_service.py` 新增失败用例：存在的本地 PNG 图片行导出 md 后改写为 `data:image/png;base64,` 且可解码回原字节
- [ ] 1.2 新增失败用例：缺失图片行导出后被跳过，不残留死路径引用
- [ ] 1.3 新增失败用例：无图片报告导出后内容与输入一致（含免责声明）、无 data URI 注入；会话侧传入的 `report_markdown` 字符串保持原样
- [ ] 1.4 新增失败用例：非图片后缀（如 `.txt`）的本地文件引用行与远程 URL 图片行原样保留
- [ ] 1.5 运行 `uv run pytest tests/export/ -v` 确认新用例全部红、存量用例仍绿

## 2. 最小实现（TDD 绿）

- [ ] 2.1 `src/finance_agent/export/service.py` 新增 `embed_images_as_data_uris(markdown_text) -> str`：`_IMAGE_LINE_RE` 逐行识别、固定后缀映射表、`base64.b64encode` 内嵌
- [ ] 2.2 `export_report` md 分支在 `append_disclaimer` 后接入 embed，docx/pptx/pdf 路径与 `sanitize_missing_images` 共用逻辑不变
- [ ] 2.3 `uv run pytest tests/export/ -v` 确认新用例全绿、存量用例无回归

## 3. 回归与收口

- [ ] 3.1 `uv run pytest tests/test_export_api.py -v` 通过（/api/export 契约不回归）
- [ ] 3.2 `uv run ruff check` 与 `uv run mypy` 通过
- [ ] 3.3 全量 `uv run pytest` 通过（Langfuse 在线，注意全量套件前置条件）
- [ ] 3.4 人工抽查：容器或本机起后端跑一次导出，下载 md 用本地渲染器确认图片可见、文件自包含，结论记入 `tests/validation/`
