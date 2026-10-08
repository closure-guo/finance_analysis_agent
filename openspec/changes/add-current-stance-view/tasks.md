# Tasks: add-current-stance-view

## 1. 后端

- [x] 1.1 `model.py` 新增 `list_current_predictions(source_type=None, db_path=None)`：每股最新一条 open（join 子查询 + prediction_id tiebreak），单测覆盖——同股多条 open 仅返回最新 / 无 open 标的不出现 / dup 与已结算行不进入 / source 过滤 / 空库（commit 069b79fc，37 passed）
- [x] 1.2 `api.py` 新增 `GET /api/v1/track-record/current`（可选 `source` 参数、as_of、disclaimer），集成测试覆盖响应结构与回测实盘分离（commit ce2caa07，29 passed）

## 2. 前端

- [x] 2.1 类型定义 + `TrackRecordPage` 新增「当前观点」区：每股一行（标的/方向/建立日期/入场价/判定窗口/状态）、口径说明副标题、行点击进详情、空态文案、testid（`current-stance`/`current-stance-row-{id}`/`current-stance-empty`）、独立错误边界（含畸形 200 守卫：违约走显式失败态，IndexCompareCard 同款；commit 647cc036，tsc 零错误）
- [x] 2.2 前端单测：区块渲染 / 空态 / 加载失败显式文案（行点击导航归 E2E 覆盖——分层修正，见 3.1）

## 3. 门禁与验证

- [x] 3.1 E2E spec 覆盖核心交互场景（区块渲染、每股收敛、台账不受影响、行点击导航），scan.sh P0=0 + task-reviewer 深审通过；空态由 vitest 覆盖（串行共享持久库无法构造全空前提，豁免理由落盘 spec 头注释）（commit 162b3fc7，专属套件 9/9）
- [x] 3.2 `uv run ruff check` 全绿；`uv run mypy src` 83 errors 与基线持平（零新增）；`uv run pytest` 4267 passed（2 个存量 @live 提供商失败已在基线复现，与本变更无关）；`cd frontend && npm test` 654/654；E2E 专属套件 `tests/e2e/playwright`（playwright.track-record.config.ts）9/9——默认 stub 套件与本变更无交集，且 incident 038 教训下不与生产容器共存跑默认端口，由 CI 兜底
- [x] 3.3 人工验证报告落 `tests/validation/`（真实数据抽查：每股一条、台账不变、行点击）（tests/validation/2026-10-08-add-current-stance-view-validation.md：13 标的 13 行、601066 收敛到 10-08、台账 73 行不变、行点击详情跳转、300750 T+252 如实披露、截图视觉核验通过）
