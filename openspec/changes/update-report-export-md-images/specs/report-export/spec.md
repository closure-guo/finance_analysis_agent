## MODIFIED Requirements

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
- **THEN** 系统生成 `.md` 单文件（除图片行按「Markdown 导出图片自包含」改写为内嵌 data URI 外，内容与会话存取的 `report_markdown` 一致，含免责声明）
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

## ADDED Requirements

### Requirement: Markdown 导出图片自包含

系统 SHALL 在导出 Markdown 格式时，将报告中引用且源文件仍存在的本地位图图片行（png/jpg/jpeg/gif/webp）改写为 base64 data URI（`data:image/<mime>;base64,<编码>`）内嵌于 `.md` 文件，使导出产物为不依赖任何外部文件的自包含单文件。改写 SHALL 仅发生在导出时刻：会话存储的 `report_markdown` SHALL 保持原样（仍为文件路径引用）。图片源文件已不存在时，系统 SHALL 跳过该图片行继续导出，不因缺失图片而失败。

#### Scenario: 图片源文件存在时内嵌为 data URI

- **GIVEN** 报告 Markdown 含 `![标题](/tmp/finance_charts/600519/chart_roe.png)` 且该 PNG 文件存在
- **WHEN** 系统导出 md
- **THEN** 落盘 `.md` 中该图片行为 `![标题](data:image/png;base64,<PNG 的 base64 编码>)` 形式
- **AND** `.md` 为单个文件，不含指向临时目录或本机绝对路径的图片引用

#### Scenario: 图片源文件缺失时优雅降级

- **GIVEN** 报告 Markdown 含 `![标题](路径.png)` 且该 PNG 文件已不存在（如历史会话的临时目录已清理）
- **WHEN** 系统导出 md
- **THEN** 该图片行被跳过，其余内容完整落盘
- **AND** 不抛异常，产物中不残留引用不存在路径的图片行

#### Scenario: 会话存储的 report_markdown 不被改写

- **GIVEN** 某会话存有含图片行（文件路径引用）的 `report_markdown`
- **WHEN** 对该会话执行 md 导出（按需或管线自动）
- **THEN** 该会话的 `report_markdown` 保持文件路径引用原样
- **AND** 仅有导出落盘的 `.md` 文件包含 data URI

#### Scenario: 无图片报告原样导出

- **GIVEN** 报告 Markdown 不含任何图片行
- **WHEN** 系统导出 md
- **THEN** 产物内容与 `report_markdown`（含统一免责声明追加）一致，不注入任何 data URI
