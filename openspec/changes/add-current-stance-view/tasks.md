# Tasks: add-current-stance-view

## 1. 后端

- [ ] 1.1 `model.py` 新增 `list_current_predictions(source_type=None, db_path=None)`：每股最新一条 open（join 子查询 + prediction_id tiebreak），单测覆盖——同股多条 open 仅返回最新 / 无 open 标的不出现 / dup 与已结算行不进入 / source 过滤 / 空库
- [ ] 1.2 `api.py` 新增 `GET /api/v1/track-record/current`（可选 `source` 参数、as_of、disclaimer），集成测试覆盖响应结构与回测实盘分离

## 2. 前端

- [ ] 2.1 类型定义 + `TrackRecordPage` 新增「当前观点」区：每股一行（标的/方向/建立日期/入场价/判定窗口/状态）、口径说明副标题、行点击进详情、空态文案、testid（`current-stance`/`current-stance-row-{id}`/`current-stance-empty`）、独立错误边界
- [ ] 2.2 前端单测：区块渲染 / 空态 / 行点击导航

## 3. 门禁与验证

- [ ] 3.1 E2E spec 覆盖核心交互场景（区块渲染、空态、行点击导航），scan.sh + e2e-reviewer 通过
- [ ] 3.2 `uv run ruff check` / `uv run mypy` / `uv run pytest` 全绿；`cd e2e && npx playwright test`（stub 套件）全绿
- [ ] 3.3 人工验证报告落 `tests/validation/`（真实数据抽查：每股一条、台账不变、行点击）
