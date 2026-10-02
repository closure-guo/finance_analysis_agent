## Why

md 导出把报告图表 PNG 的**临时目录绝对路径**原样写进单个 `.md` 文件（`charts.py` 存图于 `tempfile.gettempdir()/finance_charts/`，`report.py` 以 `![标题](绝对路径)` 嵌入，`service.py` md 分支直接落盘文本、图片不跟随）。容器部署时该路径仅容器内存在且重启即失，本机运行时为 Windows 反斜杠路径（多数渲染器无法解析），下载到他机则彻底无解——用户拿到的 md 图全部裂开。docx/pdf/pptx 因转换时读图嵌入不受影响，唯独 md 是纯文本外链。现有 spec 对 markdown 格式只定义了「内容与 `report_markdown` 一致 + 免责声明」，未定义图片可解析性，属于行为未定义，需先立 delta 再实现。

## What Changes

- md 导出（管线自动生成 `generate_file` 与 `POST /api/export` 共用 `export_report`，行为同步变化）：落盘前将 markdown 中引用**存在**的本地 PNG 图片行改写为 `data:image/png;base64,...` 内嵌 data URI，产出单文件自包含 md。
- 图片源文件已不存在（如历史会话临时目录已清理）时沿用现有 `sanitize_missing_images` 降级：跳过该图片行，不失败——与 PDF 格式的既有降级行为一致。
- 会话存储的 `report_markdown` **保持不变**（仍存文件路径）；改写仅发生在导出时刻，会话存储体积与前端报告视图不受影响。
- docx/pptx/pdf 三格式、`/api/files` 列表/下载/删除接口、前端下载中心契约均不变。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `report-export`：① MODIFIED「按需导出接口」——「Markdown 格式导出」场景从「内容与 `report_markdown` 一致」改为「除图片行改写为内嵌 data URI 外内容一致」；② ADDED「Markdown 导出图片自包含」——定义导出时刻改写、源文件存在性判定、缺失降级、单文件契约与 `report_markdown` 不变性。

## Impact

- **代码**：`src/finance_agent/export/service.py`（md 分支新增图片行改写逻辑；`sanitize_missing_images` 与改写顺序需在同一遍处理或明确先后）。
- **API**：无契约变化（`POST /api/export`、`GET /api/files` 仍单文件模型）；md 文件体积从数十 KB 增至约 2–4 MB（13 张 150dpi PNG 编码膨胀 ≈33%），与内嵌图片的 PDF 同量级。
- **会话存储**：`report_markdown` 不变。
- **前端**：无改动。
- **测试**：`tests/` 新增 md 导出图片改写单测（存在→data URI、缺失→跳过、无图→原样、`report_markdown` 不被污染）。
