# report-export delta: add-download-center

## ADDED Requirements

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
