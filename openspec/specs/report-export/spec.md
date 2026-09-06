# Report Export Specification

## Purpose

定义报告文件导出的能力域：`POST /api/export` 按需导出单文件（pdf/word/markdown）、服务端 PDF 渲染（中文/表格/图片/优雅降级）、管线自动生成的 `file_paths` 四键契约。导出服务对管线和用户双向复用，任何单格式失败不阻断其余。
## Requirements
### Requirement: 按需导出接口

系统 SHALL 提供按需导出接口 `POST /api/export`，接收 `{session_id, fmt}`，从该会话读取 `report_markdown` 现场生成**单一**文件（每次请求只产出一个文件），并返回可下载的 URL；导出不要求该会话处于 completed 状态，只要会话内存在 `report_markdown` 即可。

#### Scenario: 当前会话导出 PDF

- **GIVEN** 某会话已完成分析且存有 `report_markdown`（当前屏幕报告所属会话）
- **WHEN** 客户端向 `/api/export` 发送 `{"session_id": "<id>", "fmt": "pdf"}`
- **THEN** 系统以该会话的 `report_markdown` 现场生成 PDF 文件
- **AND** 响应返回 `{"file_name": "<name>.pdf", "url": "/api/files/<name>.pdf"}`
- **AND** 通过 `GET /api/files/<name>.pdf` 可下载该文件

#### Scenario: 历史会话导出 Word

- **GIVEN** 某历史会话存有 `report_markdown`，但管线结束时自动生成的文件已被清理（`reports/` 下无对应产物）
- **WHEN** 客户端请求 `{"session_id": "<old_id>", "fmt": "word"}`
- **THEN** 系统从该会话的 `report_markdown` 重新生成 `.docx` 文件并返回下载 URL（不依赖旧自动产物）

#### Scenario: Markdown 格式导出

- **WHEN** 客户端请求 `{"session_id": "<id>", "fmt": "markdown"}`
- **THEN** 系统生成 `.md` 文件（内容与会话存取的 `report_markdown` 一致，含免责声明）
- **AND** 返回该文件的下载 URL

#### Scenario: 会话不存在返回 404

- **GIVEN** `session_id` 对应的会话不存在或无 `report_markdown`
- **WHEN** 客户端发起导出请求
- **THEN** 系统返回 HTTP 404 与明确错误信息，不生成任何文件

#### Scenario: 不支持的格式返回 400

- **WHEN** 客户端请求 `{"session_id": "<id>", "fmt": "exe"}`
- **THEN** 系统返回 HTTP 400 与「不支持的导出格式」错误信息

#### Scenario: 转换失败返回 500

- **GIVEN** 会话存在且格式受支持，但文件转换异常（如渲染引擎失败）
- **WHEN** 客户端发起导出请求
- **THEN** 系统返回 HTTP 500 与错误信息
- **AND** 不残留半成品下载 URL

### Requirement: 服务端 PDF 生成

系统 SHALL 在服务端将报告 Markdown 渲染为多页 PDF 文档，支持中文文本、表格、页眉页脚，并将报告中引用的 PNG 图表图片嵌入 PDF；当图片源文件已不存在时，系统 SHALL 跳过该图片继续生成，不因缺失图片而失败。

#### Scenario: 含中文与表格的 PDF 渲染

- **GIVEN** 报告 Markdown 包含中文标题、中文段落与 Markdown 表格
- **WHEN** 系统生成 PDF
- **THEN** PDF 中中文正常显示（非豆腐块），表格按行/列正确渲染
- **AND** 生成文件以 `%PDF` 文件头开头，可被 PDF 阅读器解析

#### Scenario: 图表图片存在时嵌入

- **GIVEN** 报告 Markdown 含 `![标题](路径.png)` 且该 PNG 文件存在
- **WHEN** 系统生成 PDF
- **THEN** 图片被嵌入 PDF 对应位置

#### Scenario: 图表图片缺失时优雅降级

- **GIVEN** 报告 Markdown 含 `![标题](路径.png)` 且该 PNG 文件已不存在（如历史会话的临时目录已清理）
- **WHEN** 系统生成 PDF
- **THEN** 系统跳过该图片继续生成 PDF
- **AND** 不抛异常、不产出损坏文件

### Requirement: 导出文件契约与 file_paths 扩展

系统 SHALL 将导出格式契约统一为四键 `file_paths: {docx, pptx, pdf, md}`；管线结束自动生成的 `generate_file` 与 `report_ready` 事件 SHALL 携带扩展后的 `file_paths`，前端据此获知各格式文件是否已可下载。

#### Scenario: 管线完成时自动生成四格式

- **GIVEN** 深度分析管线执行到 `generate_file` 节点且 `final_report` 非空
- **WHEN** 管线完成并发出 `report_ready` 事件
- **THEN** `file_paths` 包含 `docx`、`pptx`、`pdf`、`md` 四个键（值为文件相对名或导出失败时的 `null`）
- **AND** 各格式文件均追加统一免责声明

#### Scenario: 单格式生成失败不阻断其他格式

- **GIVEN** 自动生成阶段某格式转换失败（如 PDF 渲染异常）
- **WHEN** `generate_file` 执行
- **THEN** 失败格式对应键值为 `null`
- **AND** 其余格式正常生成，`report_ready` 照常发出，管线不中断

### Requirement: 文件列表接口

系统 SHALL 提供 `GET /api/files` 接口，实时扫描 `REPORTS_DIR` 下的导出文件（docx/pptx/pdf/md），返回按创建时间倒序的元信息列表；每项 SHALL 包含 `file_name`、`file_type`、`size_bytes`、`created_at`（毫秒时间戳）。目录不存在或为空时 SHALL 返回空列表而非报错。

#### Scenario: 返回全部导出文件元信息

- **GIVEN** `reports/` 下存在 `a.docx`（204800 字节，创建于 t1）与 `b.pptx`（创建于 t2，t2 > t1）
- **WHEN** 客户端请求 `GET /api/files`
- **THEN** 响应为 JSON 数组，首项为 `b.pptx`
- **AND** 每项含 `file_name`、`file_type`、`size_bytes`、`created_at` 四个字段

#### Scenario: 目录为空返回空列表

- **GIVEN** `reports/` 下无任何导出文件
- **WHEN** 客户端请求 `GET /api/files`
- **THEN** 系统返回 HTTP 200 与空数组 `[]`

#### Scenario: 非导出文件被忽略

- **GIVEN** `reports/` 下存在图表 PNG 与 `.tmp` 临时文件
- **WHEN** 客户端请求 `GET /api/files`
- **THEN** 响应中 SHALL NOT 包含 PNG 与临时文件，仅含四种导出格式

### Requirement: 文件删除接口

系统 SHALL 提供 `DELETE /api/files/<file_name>` 接口，从 `REPORTS_DIR` 删除指定导出文件；删除成功返回 HTTP 200，文件不存在返回 HTTP 404。

#### Scenario: 删除存在的文件

- **GIVEN** `reports/` 下存在 `a.docx`
- **WHEN** 客户端请求 `DELETE /api/files/a.docx`
- **THEN** 系统返回 HTTP 200
- **AND** `a.docx` 从磁盘消失，后续 `GET /api/files` 不再包含该项

#### Scenario: 删除不存在的文件

- **WHEN** 客户端请求 `DELETE /api/files/nonexistent.docx`
- **THEN** 系统返回 HTTP 404，不产生任何副作用

### Requirement: 文件接口路径安全

所有以文件名为参数的文件接口（下载、删除）SHALL 将解析后的绝对路径限制在 `REPORTS_DIR` 内；含路径穿越（如 `../`、绝对路径、URL 编码绕过）的请求 SHALL 返回 HTTP 400 或 404，且不读写目标目录外任何文件。

#### Scenario: 路径穿越被拒绝

- **WHEN** 客户端请求 `DELETE /api/files/..%2F..%2F.env`
- **THEN** 系统返回 HTTP 400 或 404
- **AND** `REPORTS_DIR` 之外的文件不受影响

