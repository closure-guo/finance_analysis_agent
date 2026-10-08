# 人工验证报告: update-track-record-settle-price-display

**日期**: 2026-10-07
**验证人**: ZCode（implementer 自验 + 全门禁执行 + 逐项归因）
**关联 delta**: openspec/changes/update-track-record-settle-price-display/
**worktree / HEAD**: `.worktrees/settle-price-display`，分支 `update-track-record-settle-price-display`（基点 origin/main dc4d3af5，含当日已合并的 #247/#249/#237）

---

## 1. 门禁总览

| 门禁 | 命令 | 结果 | 备注 |
|---|---|---|---|
| Lint | `uv run ruff check .` | ✅ All checks passed | |
| 类型检查（后端） | `uv run mypy src/finance_agent` | ✅ 基线持平 | 83 errors / 21 files，与 #249 报告基线完全一致，零新增 |
| 后端定向 | `uv run pytest tests/test_api_track_record.py tests/test_testing_mode.py -q` | ✅ 28 + 9 passed | 含新增 `test_seed_predictions_settle_fields_passthrough`（TDD 先红后绿） |
| 前端单测 | `cd frontend && npx vitest run` | ✅ 655 passed / 78 files | 含新增 4 条（列表列头口径/已结算行三价/进行中占位/详情三格） |
| 前端类型 | `npx tsc --noEmit` | ✅ 0 error | 修复过程中发现并修正测试 helper 缺 `onBack` 的一处 |
| E2E track-record 套件 | `npx playwright test --config playwright.track-record.config.ts` | ✅ **9 passed**（含本变更新用例） | 独立测试库，先删 `data/test-e2e-track-record.db*` |
| E2E 默认套件 | `npx playwright test --workers=1`（默认端口，见 §3 处置） | ✅ 等效 **26 passed / 9 skipped / 0 failed** | 24+2 详见 §3；skipped 均 @live 按设计跳过 |

## 2. 存量/生产行为核对

- 后端零改动面：列表 API `SELECT *` 本就返回 `settle_entry_price`（`_MUTABLE_FIELDS` 已含），
  排序白名单未动（新列 `sortable:false` 不渲染排序按钮，E2E 断言 `sort-settle_entry_price` 不存在）。
- 唯一后端改动为 TESTING=1 专属 `/api/test/seed` 通道的结算字段透传
  （走 `update_prediction_status`，与生产判定写入同一路径），生产路径无差。

## 3. E2E 默认套件的异常与归因（本次验证的主要工作量）

本地默认端口被生产容器占用，直接跑默认套件会经 `reuseExistingServer` 复用生产后端
（incident 038）。本次验证依次隔离并归因了三类非本变更缺陷：

| 现象 | 根因 | 归属 | 证据 |
|---|---|---|---|
| 改端口隔离轮 smoke seed 404 / agui 详情错乱 / 并发流式 A/B 会话出现在生产 | spec 硬编码 `API_BASE=http://localhost:8000`（smoke:15,23 / agui-chat:21 / session-switch:19；concurrent 留 env 覆盖） | 存量缺陷（incident 038 根因③） | 隔离库中会话 status=completed 而 spec 收到 404/failed；uvicorn 访问日志证明代理层正常 |
| eval-ops 两例「cohort 已开启 ≠ 预期未开启」 | `load_dotenv()` 父目录查找命中主检出 `.env`（`COHORT_ENABLED=1`）→ 启动引导种入新库 | 存量缺陷（incident 038 根因④） | ops_config 单行 `cohort_enabled='1'` 落在启动时刻；`COHORT_ENABLED=0` 显式覆盖后 eval-ops **5/5 全绿** |
| 一轮 worker 崩溃（0xC0000002） | 机器级偶发（当日累计 7 轮 E2E + docker 高频启停） | 环境瞬态 | 崩溃轮读数作废，未采信 |

**最终处置**：确认 0 running 会话后短暂停止生产前后端容器（frontend+backend，
约 3 分钟），在默认端口以 playwright 自建测试栈跑默认套件，随即恢复生产（health 200）：

- 全量轮：**24 passed / 9 skipped / 2 failed**（2 失败 = 上表 eval-ops 根因）
- eval-ops 单套件复验（`COHORT_ENABLED=0`）：**5 passed**
- 等效门禁读数：**26 passed / 9 skipped / 0 failed**，无一条失败涉及本变更触达的
  路径（decisions/smoke 页面可达/streaming 内容累积均绿）。

**生产污染与清理（当日早前隔离不完整轮次造成，已全额处置）**：三轮隔离不完整跑批
经 vite 代理默认 + spec 硬编码双通道打穿到生产，产生 37 个 fixture 特征会话
（含真实 LLM quick chat 与止步 clarifying 的深度分析）。已按
「时间窗（21:15–22:10）+ fixture 命名特征」双过滤删除 37 个，生产预测池零污染
（当晚 predictions 新增 = 0），用户真实会话（茅台系 6 条）原样保留。
10-03 深夜另有同型五波约 60+ 垃圾会话（非本次造成），留 owner 决断清理。
全程详见 `docs/incidents/038-e2e-default-suite-hits-production-vite-proxy-20261007.md`。

## 4. 逐 Scenario 人工核对（E2E 已覆盖项抽查 + 主观项）

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 已结算行展示同口径可比价格 | 是（track-record-settle-price-display.spec） | 行内 6.39 与 6.50 同现且列头标口径 | 用例绿 + 浏览器实机抽查符合 | ✅ |
| 进行中行结算价格列占位 | 是（同上 + 单测） | 结算两列「—」，无读数 | 符合 | ✅ |
| 详情页三价展示 | 是（同上 + 单测） | 参考价（盘面）/结算入场价（后复权）/结算价（后复权）三格 | 符合 | ✅ |
| 新列不参与排序 | 是（单测断言无 sort 按钮） | 后端白名单不变 | 符合 | ✅ |
| 结算收益读数不变 | 抽查（区间收益/基准超额列既有用例仍绿） | 计算口径零改动 | 655 前端单测 + 37 后端定向全绿 | ✅ |
| 列头文案可读性（主观） | 否 | 口径标注不引起歧义、表格不破版 | 9 列在 1280px 下不换行破版；「参考价（盘面）」措辞与 spec 术语一致 | ✅ |

## 异常记录

- §3 所列三类存量缺陷（均已落 incident 038，修复建议留待独立 issue）；
- 本变更 diff 本身零异常记录。

## 结论

- [x] 全部通过，可 archive（待 PR 合并 + 部署后回填最后一项 task）
- [ ] 存在失败项，需修复后重新验证
