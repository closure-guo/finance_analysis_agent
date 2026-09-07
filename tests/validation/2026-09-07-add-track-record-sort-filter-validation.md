# 人工验证报告: add-track-record-sort-filter

**日期**: 2026-09-07
**验证人**: ZCode（浏览器自动化实测，DOM 快照为证据）
**关联 delta**: openspec/changes/add-track-record-sort-filter/
**E2E 门禁**: 不适用（`e2e/` Playwright 基础设施 §5.6 P1–P4 未落地，门禁尚未生效；覆盖由前端 RTL 单测 + 后端集成测试 + 本次浏览器实测承担）

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 建立日期列展示 | 否（RTL 单测覆盖） | 表格展示 `created_at` 日期部分，可排序 | 表头「建立日期 ↓」，行首展示 yyyy-mm-dd | ✅ |
| 按列排序 | 否（RTL 覆盖） | 点击列头切换升/降序并显示指示 | 点「区间收益」→ 表头变「区间收益 ↑」，建立日期指示消失 | ✅ |
| 关键字过滤 | 否（RTL 覆盖） | 只显示代码/名称/方向/状态匹配记录 | 输入「茅台」+ 查询 → 仅余 600519.SH 记录 | ✅ |
| 时间段过滤（到日、含两端） | 否（RTL 覆盖） | 按创建日过滤，含两端 | 2026-09-01 至 2026-09-07 → 12 条，两端记录均在 | ✅ |
| 过滤组合 | 否 | 关键字 + 时间段同时生效 | 茅台 + 09-01~09-07 → 12 条 | ✅ |
| 重置 | 否（RTL 覆盖） | 清空过滤与排序，恢复全量 | 重置后回到 44 条 + 建立日期 ↓ 默认排序 | ✅ |
| 分页 | 否（RTL 覆盖 page=2 请求） | 超过单页显示分页并翻页 | 当前库 44 条 < 50，单页（第 1/1 页，按钮禁用态正确）；多页翻页由 RTL 单测断言 page=2 请求 | ✅ |
| 过滤后 total 反映子集 | 否（集成测试覆盖） | total = 过滤后条数 | 后端 curl：keyword=茅台 → 16；日期区间 → 24；API 用例断言 total 一致 | ✅ |

> 后端 API 另经 curl 实测：`sort_by=created_at&sort_dir=asc` 首条为最早创建记录；非法 `sort_by=bogus` 回退默认排序不报错（由集成测试断言）。

## 异常记录

1. **E2E 门禁缺口**：`e2e/`（独立 Playwright TS 项目）尚未在本仓库落地（§5.6 P1–P4 未完成），按 §4.5 本周期门禁不生效。交互场景改为：前端 RTL 单测（16 用例全绿）+ 后端集成测试（14 用例全绿）+ 本次浏览器人工实测。待 E2E 基建落地后，应补 `track-record 排序/过滤/分页` 的 E2E spec。
2. **验收环境既有失败（与本 delta 无关）**：全量后端 pytest 有 20 个失败，全部位于 `tests/test_citation*.py`（会话开始时工作区已存在未提交的引用方向词表改动）与 `tests/test_trace_content_live.py`（@live 真实 LLM 用例，仅 nightly 运行）。本 delta 涉及的 `tests/outcome/test_track_record_model.py`、`tests/test_api_track_record.py`、`frontend/src/test/trackRecord/trackRecordPage.test.tsx` 全部通过。
3. **前端 tsc 既有报错（与本 delta 无关）**：`PredictionDetailPage.tsx:121` 引用 `rationale_snapshot` 而 `PredictionRecord` 类型无该字段——`frontend/src/types.ts` 与 `PredictionDetailPage.tsx` 相对 HEAD 无任何改动，属 main 既有问题；本次改动文件 `tsc` 无新增报错。

## 结论

- [x] 全部通过，可 archive
- [ ] 存在失败项，需修复后重新验证