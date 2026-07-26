# 人工验证报告: add-e2e-test-infrastructure

**日期**: 2026-07-26
**验证人**: [agent]
**关联 delta**: openspec/changes/add-e2e-test-infrastructure/

## E2E 门禁

playwright-report 路径: tests/e2e/playwright/playwright-report/

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 前端首页可达 | 是（smoke.spec.ts） | page.goto('/') + 标题匹配 | page.goto('/') 成功，标题匹配 `/Finance Analysis Agent/i`，耗时 27.0s | ✅ |
| 后端 /api/health 返回 200 | 是（smoke.spec.ts） | GET /api/health -> 200 + {"status":"ok"} | 200 + `{"status":"ok"}`，耗时 349ms | ✅ |
| TESTING=1 下 /api/test/seed 可用 | 是（smoke.spec.ts） | POST /api/test/seed -> 200 + mode:testing | 200 + `{"status":"ok","mode":"testing"}`，耗时 353ms | ✅ |
| 非 TESTING 下 /api/test/seed 404 | 否（单元测试覆盖） | 单元测试 7/7 passing | 7/7 passing（`tests/test_testing_mode.py`，2.80s） | ✅ |

## 异常记录

无

### E2E 运行明细

- 命令：`cd tests/e2e/playwright && npx playwright test`
- 退出码：0
- 结果：3 passed (37.8s)
- 工作进程：3 workers（fullyParallel）
- WebServer：后端 uvicorn（TESTING=1）+ 前端 vite dev server 均成功启动
- WebServer 日志显示 LiteLLM 远程模型价格表抓取失败（网络/DNS），自动 fallback 到本地备份，不影响门禁结果

### 单元测试运行明细

- 命令：`uv run pytest tests/test_testing_mode.py -v`
- 退出码：0
- 结果：7 passed, 2 warnings in 2.80s
- 覆盖：TESTING 开关常量、/api/test/seed 与 /api/test/reset 在两种模式下的行为、/api/health 双模式可用性

## 结论

[x] 全部通过，可 archive
[ ] 存在失败项，需修复后重新验证
