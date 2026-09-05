# Tasks: expose-decision-outcomes

## 1. 后端只读查询层

- [x] 1.1 `outcome/store.py` 新增 `list_decisions`（ticker/status 过滤 + 倒序 + limit 上限）与 `decision_stats`（SQL 聚合：计数、胜率、均值，null 口径符合 spec），TDD 覆盖空表/全 open/含 null excess 边界
- [x] 1.2 api.py 新增 `GET /api/decisions` 与 `GET /api/decisions/stats`，非法 status 返回 422，集成测试直连 API 验证过滤组合与统计口径

## 2. 前端战绩页面

- [x] 2.1 新增 `frontend/src/pages/decisions/` 战绩页面：汇总卡 + 决策列表 + 状态/股票过滤 + 空态，收益红涨绿跌与 null 占位「—」符合 spec
- [x] 2.2 App.tsx 注册 `/decisions` pathname 路由，侧边栏折叠/展开两态均有入口（参照下载中心模式）
- [x] 2.3 决策行可跳转来源会话；会话已删除时 toast 提示不崩溃

## 3. 验收门禁（交互类变更）

- [x] 3.1 E2E spec 覆盖核心场景：页面渲染汇总+列表、过滤联动、空态、结算后刷新可见新状态（playwright-test-generator 真实探索取 selector，scan.sh P0 清零 + e2e-reviewer 通过）
- [x] 3.2 E2E 门禁全绿（`cd tests/e2e/playwright && npx playwright test tests/decisions.spec.ts --workers=1`；全量套件 11 例既有失败与本 delta 无关，见验证报告异常记录）
- [x] 3.3 `uv run pytest`（门禁 `-m "not live"`）与 `cd frontend && npm test` 全绿
- [x] 3.4 人工验证报告落 `tests/validation/`（含战绩数字与 decision_log 直查核对、跳转会话体验确认；待人工抽查项已明列）
