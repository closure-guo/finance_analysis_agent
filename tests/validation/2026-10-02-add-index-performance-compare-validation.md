# 人工验证报告: add-index-performance-compare

**日期**: 2026-10-02
**验证人**: ZCode(agent,自动化部分)+ [待人工补签]
**关联 delta**: openspec/changes/add-index-performance-compare/
**E2E 门禁**: tests/e2e/playwright/playwright-report/(默认套件)+ 专属套件 playwright.track-record.config.ts(3 passed)

## 验证结果

| Scenario | E2E 已覆盖? | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 无数据空态(卡片可见+空态文案) | 是(track-record-index-compare.spec.ts #1) | index-compare-empty 可见 | 自动化通过 | ✅ |
| 造数后摘要/对比条/分色(跑赢绿↑跑输红↓灰显) | 是(#2) | 跑赢 2/4 个指数;000300↓跑输;000905↑跑赢;399006 无数据 | 自动化通过 | ✅ |
| 跨度偏好决定请求参数(span=3m) | 是(#3) | 请求含 span=3m | 自动化通过 | ✅ |
| 卡片视觉(间距/对齐/分色与主题一致) | 否 | 与战绩页既有卡片风格一致 | **待人工抽查** | ☐ |
| 真实指数读数与行情源一致 | 否 | 5 指数区间收益与行情软件同期数字误差 <0.1pct | **待生产回填后人工核对**(见运行手册) | ☐ |
| 起算日标注(基期回退时显示「自 X 起算」) | 组件单测覆盖 | 000300 effective_start_date≠窗口首日时标注 | 单测通过 | ✅ |

## 自动化验证证据(2026-10-02,worktree .worktrees/index-compare)

- `uv run ruff check`: All checks passed
- `uv run mypy src/`: 81 errors——与 main 基线完全相同(81),**零新增**;CI 对既有第三方 stub 错误以 `|| true` 容忍
- `uv run pytest`(全量): **3949 passed** / 7 skipped / 2 failed——两失败均为既有问题:①`test_fm_decision_live_report`(@live,main 基线同挂,需 live 环境);②`test_long_task_dispatch_returns_without_blocking`(事件循环时序测试,main 与分支隔离运行均过 ×2,全量 15 分钟高负载下抖动)
- `cd frontend && npm test`: **630 passed**(76 文件)
- E2E 默认套件(TESTING=1 stub): **24 passed / 2 skipped(@live)**
- E2E track-record 专属套件(独立测试库): **3 passed**
- E2E timeline 套件: **30 passed / 1 flaky(重试通过,既有 pipeline-eta-banner 抖动) / 1 skipped**
- 本地复跑专属套件前需删 `data/test-e2e-track-record.db*`(残留种子会打破 test 1 空态;CI 全新 runner 不受影响)

## 生产部署运行手册(合并 PR 后执行)

1. `docker compose up -d --build backend`(镜像含新代码后 index-compare 端点才存在)
2. 容器内回填(近 280 交易日): `docker exec finance-agent-backend-1 python -c "from finance_agent.outcome.track_record.index_compare import sync_index_closes; print(sync_index_closes(days=280))"`;抽验: `...model import list_index_closes; print(len(list_index_closes('000300')), list_index_closes('000300')[-1])`(应 ≥200 行)
3. 冒烟: `curl -s "http://127.0.0.1:8000/api/v1/track-record/index-compare?span=all"` → 五指数读数
4. 人工核对上表「真实指数读数」行(与东方财富/同花顺同期区间涨跌幅比对)后勾选
5. 注意:东财行情域本机曾不可达(冒烟时走了新浪回退源);若 `failed` 非空,按 AGENTS.md 纪律先归因再处置

## 异常记录

- 无阻断性异常。已记录非阻断项:①`/api/test/reset` 仍为占位骨架,专属套件本地复跑需手动删库(挂账后续任务);②mypy 81 个既有错误与本次无关

## 结论

[ ] 全部通过,可 archive
[ ] 存在失败项,需修复后重新验证

> 结论栏待人工完成「卡片视觉」与「真实读数」两项抽查后勾选(后者需先执行生产运行手册 1-3 步)
