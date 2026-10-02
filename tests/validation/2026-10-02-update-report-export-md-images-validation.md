# 人工验证报告: update-report-export-md-images

**日期**: 2026-10-02
**验证人**: Closure（agent 执行，人复核）
**关联 delta**: openspec/changes/update-report-export-md-images/
**E2E 门禁**: 不适用（纯后端导出逻辑变更，不含前端 UI / SSE / 会话切换 / 状态流转，按 project-workflow §2 判别非交互类）

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 存在的本地 PNG 导出后内嵌为 data URI | 否（后端单测覆盖） | `![标题](data:image/png;base64,…)` 且解码字节 == 源 PNG | 抽查：2 张真实 matplotlib PNG 走 `export_report` 全链路，2 图片行均 data URI 化，`base64.b64decode` 与源文件字节级一致 | ✅ |
| 产物无绝对路径残留（自包含） | 否 | md 中无临时目录路径 | 抽查：`str(tmp) not in content` 断言通过 | ✅ |
| 缺失图片行跳过（历史会话降级） | 否 | 行被删除、不失败 | 单测 `test_export_report_md_drops_missing_image_line` 绿；与 PDF 既有降级一致 | ✅ |
| 无图报告不注入 data URI | 否 | 内容与 report_markdown（含免责声明）一致 | 单测 `test_export_report_md_no_data_uri_without_images` 绿 | ✅ |
| 会话侧 `report_markdown` 不被改写 | 否 | 仍为文件路径引用 | 抽查断言 + 结构保证（embed 为纯函数、仅落盘产物含 data URI） | ✅ |
| 解码回读图片可正常渲染 | 否 | data URI 解码即有效 PNG | 抽查：解码落盘后图像查看器确认为有效折线图 | ✅ |
| docx/pptx/pdf 与 /api/files 契约零回归 | 否 | 存量行为不变 | `tests/export/` + `tests/test_export_api.py` 27 passed / 2 skipped（既有 weasyprint 环境跳过） | ✅ |

## 静态门禁与全量回归

| 命令 | 结果 | 证据 |
|---|---|---|
| `uv run pytest tests/export/ tests/test_export_api.py`（HEAD=c2b0b511 新鲜复跑） | 27 passed / 2 skipped | 本报告抽查执行 |
| `uv run pytest`（全量） | Task 1 @ b5bcdf10: 3902 passed / 1 failed / 7 skipped；Task 2 @ c2b0b511: 3905 passed / 1 failed。唯一失败 `test_fm_decision_live` 为 @live 环境性预存失败（单独运行即 SKIP；Task 1 implementer 以 stash 对照实验证明与本次改动无关） | .superpowers/sdd/task-1-report.md、task-2-report.md |
| `uv run ruff check` | All checks passed! | 本报告抽查执行 |
| `uv run mypy src/` | 存量 81 错（CI 咨询性 `|| true`）；改动文件 `service.py` base 与 HEAD 均 0 错——零增量 | 本报告抽查执行 |

## 人工抽查方法记录

- 合成含 2 张真实 PNG（matplotlib 生成）的中文报告 markdown，`export_report(..., formats=("md",))` 落盘；
- 程序化断言：图片行数=2、全部 `data:image/png;base64,` 前缀、无临时目录路径、解码字节==源字节、免责声明在场、会话侧原文未污染；
- 解码第一张 data URI 落盘后图像查看器确认渲染正常。
- 说明：抽查用合成图的标题在无中文字体环境下造图时有豆腐块，属验证脚本造图环境现象，与导出链路无关；生产图表在 Docker 内带中文字体生成。
- 待人复核项：在真实管线跑一次深度分析并从下载中心下载 md，本地渲染器（VS Code 预览/Typora）目验图片可见、文件可单独拷走。

## 异常记录

（无阻塞异常。附注：全量套件存在既有 `@live` 用例在全量运行时因 `.env` 加载泄漏发起真实请求的预存问题，与本变更无关，建议另行立 issue 排查。）

## 结论

- [x] 全部通过，可 archive（待人复核项完成即可归档）
