# Proposal: add-download-center

## Why

报告导出文件（docx/pptx/pdf/md）目前只能在生成它的会话内逐个点击下载，存在三个问题：

1. **无统一入口**：用户无法一览所有已生成文件，历史报告文件只能回到对应会话翻找。
2. **无管理能力**：`reports/` 下文件只增不减，用户无法从前端删除过期文件，磁盘占用不可控。
3. **体验断层**：同类产品（如 Kimi）均提供独立的下载管理页，用户已形成「侧边栏入口 → 文件列表 → 下载/删除」的心智预期。

## What Changes

- **后端文件列表接口**：新增 `GET /api/files`（无参），扫描 `REPORTS_DIR`，返回文件元信息列表（文件名/类型/大小/创建时间），按创建时间倒序。
- **后端文件删除接口**：新增 `DELETE /api/files/<file_name>`，删除指定导出文件。
- **路径安全**：列表/下载/删除三类文件接口统一做路径校验，目标必须解析在 `REPORTS_DIR` 内，拒绝路径穿越。
- **前端下载管理页**：新增 `/downloads` 路由页面——文件列表（类型图标、名称、大小、时间）、搜索过滤、类型筛选 tab、下载（loading 态）、删除（二次确认 + 行收起动画）、空/加载/错误三态。
- **侧边栏入口**：侧边栏底部区域新增「下载管理」菜单项，点击进入 `/downloads`。
- **交互动效规范**：列表 stagger 入场、行 hover 过渡、删除行高度收起、toast 反馈，统一时长档位并尊重 `prefers-reduced-motion`。

非目标（Out of scope）：

- 不改变 `POST /api/export` 按需导出契约与 `file_paths` 四键契约。
- 不做文件在线预览，仅下载。
- 不新建数据库表，文件元信息实时扫描生成。
- 不做批量操作（批量下载/批量删除）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `report-export`: 新增文件列表接口、文件删除接口两条契约；文件类接口统一路径安全校验要求。
- `frontend`: 新增下载管理页（路由、列表、筛选、下载/删除交互、三态）与侧边栏入口；新增交互动效规范。

## Impact

- **后端**：`src/finance_agent/api.py`（新增 `GET /api/files`、`DELETE /api/files/<file_name>`，路径校验工具函数）。
- **前端**：`frontend/src/` 新增 `pages/downloads/`（页面 + 列表行组件）、侧边栏组件加入口项、路由表注册 `/downloads`。
- **测试**：后端接口测试（列表元信息正确性、删除生效、路径穿越拒绝）；前端组件测试（筛选/搜索/删除确认/空态）。
- **验证**：新增交互页面，人工验证报告落 `tests/validation/`；按红线需 E2E 门禁。
