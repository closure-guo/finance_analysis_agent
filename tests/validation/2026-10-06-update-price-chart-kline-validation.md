# 人工验证报告: update-price-chart-kline

**日期**: 2026-10-06
**验证人**: （待 owner 实跑后签字）
**关联 delta**: openspec/changes/update-price-chart-kline/
**E2E 门禁**: tests/e2e/playwright/playwright-report/（timeline config；默认 config 因生产 Docker 栈占用 8000/5173 未运行，见 §异常记录）

## 自动化验证证据（agent 侧已执行）

| 验证项 | 命令 | 结果 |
|---|---|---|
| 后端图表套件（数据采集+PNG+降级） | `uv run pytest tests/test_charts_kline_data.py tests/test_charts_none_series.py tests/test_charts_cjk_font.py -v` | 14/14 通过 |
| 后端全量回归 | `uv run pytest -q` | **4135 passed / 2 failed / 7 skipped**（19m15s）；2 失败均为 @live 凭据型预存（test_fm_decision_live_report、test_ark_tool_call_contract），非本 delta 引入 |
| ruff / mypy | `uv run ruff check` / `uv run mypy src` | ruff 全过；mypy 全 src 83 错/21 文件为基线，charts.py 仅 2 条预存（:869/:886，未触碰函数），**新增代码零错误** |
| 前端组件测试 | `cd frontend && npm test` | 77 文件 / 647 测试全绿 |
| 前端构建 | `cd frontend && npm run build` | 成功（chunk 体积警告为预存） |
| E2E 门禁（timeline） | `npx playwright test --config playwright.timeline.config.ts` | **exit 0：33 passed / 1 flaky / 1 skipped**（9.5m）；flaky 为预存 pipeline-hierarchical-timeline 首跑 60s 超时重试过（三 webServer 冷启资源竞争，与本 delta 无关） |
| E2E 单 spec | `npx playwright test --config playwright.timeline.config.ts report-kline-chart` | 1/1 passed（1.4m） |

## 人工验证项（待 owner 实跑）

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 真实报告 PNG 观感：250 根蜡烛密度/影线可辨/MA 标注清晰 | 否（E2E 只验证渲染发生） | 蜡烛不糊成色块，MA 图例可读 | 待验证 | ⬜ |
| 决策价位参考线位置合理性 | 否 | 入场/止损/目标三条虚线落在价格区间内、右端标签不重叠 | 待验证 | ⬜ |
| 前端 K 线交互（dataZoom 缩放/tooltip 详情） | 否 | 缩放双图联动，悬浮显示开高低收/涨跌幅/成交量 | 待验证 | ⬜ |
| 暗色主题下 K 线图可读 | 否（组件测试只验证取色机制） | 红涨绿跌在暗色下可辨，坐标轴/图例清晰 | 待验证 | ⬜ |
| 历史会话回放（升级前会话）降级为收盘折线 | 否（组件测试覆盖；E2E 无法构造历史形态会话） | 旧会话股价图显示折线，不报错不空白 | 待验证 | ⬜ |
| 导出 md/PDF 中 K 线 PNG 正确内嵌 | 部分（report-export.spec 验证导出链路，未针对新图） | 导出件包含新 K 线图 | 待验证 | ⬜ |

## 异常记录

1. **默认 E2E config 门禁未运行（环境阻塞，非本 delta 缺陷）**：生产 Docker 栈（finance-agent-backend-1/frontend-1）占用 8000/5173，且默认 config `reuseExistingServer: !process.env.CI` 会使 stub 测试打到真实后端——禁止在该状态下运行。本 delta 新增 spec 与全部管线场景在 timeline config（独立端口对 5174/5175/5176）中运行。
2. **预存基础设施缺陷（跨任务挂账，非本 delta 引入）**：`tests/test_graph_5layer.py::test_stub_keys_equal_real_fetch_keys` 以相对路径写 worktree 根 `cache.db`，会毒化同 cwd 管线 E2E 后端缓存（30 天 TTL），导致管线 spec（含存量 report-export.spec.ts）假红；本次 E2E 前须删除该缓存文件。建议独立修复（tmp_path 隔离）。
3. **预存可观测性问题（挂账）**：管线阻断时 ReAct 路径下发空 report_ready 而非可见 error，报告卡空标题渲染。

## 结论

[ ] 全部通过，可 archive
[ ] 存在失败项，需修复后重新验证

（待自动化门禁全绿 + owner 人工验证签字后勾选）
