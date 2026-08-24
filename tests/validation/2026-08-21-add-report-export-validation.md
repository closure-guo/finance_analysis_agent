# 人工验证报告: add-report-export

**日期**: 2026-08-21
**验证人**: [待人工回填]
**关联 delta**: openspec/changes/add-report-export/
**E2E 门禁**: tests/e2e/playwright/playwright-report（timeline 套件 26 passed，含 report-export.spec.ts）

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 报告卡片显示「全部文件」横幅 | 是（report-export.spec.ts） | 深度分析完成后头部出现横幅 | stub 套件实测可见 | ✅ |
| 点击横幅打开导出抽屉 | 是（report-export.spec.ts） | 右侧抽屉滑出，默认关闭时不可见 | stub 套件实测开合正常 | ✅ |
| 抽屉列出三种格式（PDF/Word/Markdown） | 是（report-export.spec.ts） | 三格式行可见 | stub 套件实测 | ✅ |
| 预览面板渲染报告正文 | 是（report-export.spec.ts） | 点预览后 Markdown 正文可滚动查看 | stub 套件实测 | ✅ |
| 关闭抽屉（按钮/Esc/遮罩） | 部分（关闭按钮在 E2E；Esc/遮罩有代码无单测） | 关闭后界面还原无遮挡 | 关闭按钮实测；Esc/遮罩需人工抽查 | ⬜ |
| 已有文件直接下载 | 否（单元/组件测试兜底） | 点击格式下载 `/api/files/{name}` | 组件测试验证 href；真实下载待人工 | ⬜ |
| 缺失文件现场生成后下载 | 否（后端单测兜底） | 点击先 POST /api/export 再下载 | 后端错误码/单测覆盖；浏览器链路待人工 | ⬜ |
| PDF 内容质量（中文/表格/图表嵌入） | 否（CI/Docker 验证） | 中文非豆腐块、表格正确、图表嵌入 | Windows 本机缺 GTK 无法产真 PDF，需 Docker/CI 目检 | ⬜ |
| 历史会话按需导出 | 否（后端单测兜底） | 任一会话可导出 pdf/word/markdown | /api/export 接口单测覆盖；真实会话待人工 | ⬜ |
| 下载失败的用户反馈 | 否 | 导出失败时 UI 提示 | 当前静默（已记 follow-up） | ⬜ |

## 异常记录

- Windows 本地缺 WeasyPrint/GTK 系统库时，`generate_file` 自动生成的 `file_paths.pdf` 为 `null`（管线不阻断，设计内降级）；`POST /api/export {fmt: pdf}` 返回 500（前端静默）。生产/CI 走 Docker（已装 libpango 等），无此问题。
- E2E stub 环境下 stub 管线的 `file_paths` 为空（三格式均走 `/api/export` 现场生成路径而非 `<a href>` 直链），属 stub 数据特征，非缺陷。
- 会话切换时抽屉自动关闭（已修复 2d2f742），需人工确认体验。

## 结论

[ ] 全部通过，可 archive
[ ] 存在失败项，需修复后重新验证
[x] 自动验证全部通过；以下主观项待人工抽查后回填并勾选：Esc/遮罩关闭、真实下载链路、Docker 内 PDF 目检、历史会话导出、下载失败反馈