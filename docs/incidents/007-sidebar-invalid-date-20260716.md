# 007 - 侧边栏会话时间显示 "Invalid Date"

| 字段     | 值          |
| -------- | ----------- |
| 编号     | 007         |
| 日期     | 2026-07-16  |
| 标题     | 侧边栏会话时间显示 "Invalid Date" |
| 状态     | 已修复      |
| 严重度   | 中（体验问题，不影响功能） |
| 发现方式 | E2E 测试（test_diagnostic.py 截图 + 人工核对） |

## 现象

会话侧边栏（Sidebar）中大量会话的时间戳显示为 `Invalid Date`，而非正常的格式化时间。
部分会话（如"贵州茅台 07-14 18:24"）可正常显示，说明问题出在特定会话的数据。

## 根因

两层问题叠加：

### 1. 数据层：历史脏数据（主因）

`data/sessions.db` 中部分会话的 `created_at` 列被错写为 session_type 的值：
- `created_at = 'chat'`（应为 ISO 时间戳，如 `2026-07-15T14:54:...`）
- `created_at = 'analysis'`

这是旧版代码/迁移导致的列错位写入。当前 `create_session` / `create_chat_session` 的 INSERT 列顺序已正确，**不再产生新脏数据**，但历史数据未清理。

### 2. 表现层：前端无兜底

`frontend/src/App.tsx`（原 L869）直接：
```js
new Date(s.created_at).toLocaleString()
```
当 `created_at` 为 `'chat'` 等非法值时，`new Date()` 返回 Invalid Date 对象，`toLocaleString()` 输出字符串 `"Invalid Date"`，前端未做兜底。

## 修复

三层防御，确保任何情况下前端都不再显示 "Invalid Date"：

### 修复 1：后端数据迁移（`src/finance_agent/session_store.py`）

`init_db()` 新增 `_repair_bad_created_at()` 迁移：把 `created_at` 列中的 `'chat'`/`'analysis'`/`''` 等非法值回退为 epoch 占位 `1970-01-01T00:00:00`。
- 无法还原真实时间（原始时间戳已丢失），用 epoch 占位
- 每次服务启动自动修复，幂等

### 修复 2：后端运行时兜底（`src/finance_agent/session_store.py`）

新增 `_normalize_created_at()` + `_is_valid_iso()`：`list_sessions()` 返回前对每条记录的 `created_at` 做校验，非法值回退为 epoch。
- 即便迁移漏网或外部直接写入脏数据，API 也返回可解析值

### 修复 3：前端兜底（`frontend/src/App.tsx`）

新增 `formatSessionTime(ts)` 纯函数：
- `null`/`undefined` -> `"未知时间"`
- `new Date(ts)` 解析失败（`isNaN`）-> `"未知时间"`
- epoch（`getTime()===0`，后端占位）-> `"未知时间"`
- 正常值 -> `toLocaleString()`

Sidebar 时间渲染改用 `formatSessionTime(s.created_at)`。

## 验证

### 单元测试

`tests/test_session_store_time.py`（6 用例，全通过）：
- 合法 ISO 时间戳原样返回
- `created_at='chat'`/`'analysis'`/`''` 兜底
- 新建 chat 会话 created_at 合法
- `init_db` 迁移修复历史脏数据

### E2E 回归

`tests/e2e/test_sidebar_invalid_date.py`：
- 侧边栏 `Invalid Date` 出现次数 = 0 ✅

### 数据修复

迁移执行后，80 个会话中残留脏数据 = 0。
后端 API 注入 `created_at='chat'` 探针，返回 `'1970-01-01T00:00:00'`（兜底生效）✅

## 部署

后端 + 前端 Docker 镜像已重建（`docker compose up -d --build backend frontend`），代码兜底在容器内生效。

## 经验

- **数据完整性校验应在前端边界兜底**：`new Date(脏值)` 不抛异常而是返回 Invalid Date 对象，静默产生错误展示。前端对所有外部时间字段都应走 `formatSessionTime` 这类兜底函数。
- **历史脏数据迁移应纳入 `init_db`**：旧版 schema/代码遗留的数据问题，靠启动时幂等迁移自动修复，避免人工 SQL。
- **列错位是 SQLite INSERT 的常见陷阱**：`INSERT INTO t VALUES (...)` 不指定列名时，列顺序依赖 schema，一旦 schema 变更极易错位。应始终用显式列名 `INSERT INTO t (col1, col2) VALUES (...)`。
