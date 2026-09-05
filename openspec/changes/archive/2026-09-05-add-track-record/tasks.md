# Tasks: add-track-record

## 1. 数据模型与迁移

- [x] 1.1 `predictions` 表幂等 DDL（append-only + 冻结字段守卫 + source_type/direction/confidence/rationale_snapshot）+ decision_log 一次性迁移脚本
- [x] 1.2 冻结字段不可改（改 direction/entry_price/快照抛 FrozenFieldError）、记录不可删除

## 2. 判定引擎与统计

- [x] 2.1 判定纯函数：horizon（默认 252/上限 1 年）+ ±2% 中性带（win/loss/neutral）+ superseded（同标的方向相反/目标价不同提前结算）+ unresolvable（停牌/退市/长期无行情）
- [x] 2.2 统计口径：胜率 = win/(win+loss)（neutral/unresolvable 不进分母）、平均超额、显著性门槛（n<10 不展示胜率/评级，10–29 标注，≥30 完整）
- [x] 2.3 日批判定任务替换现有止损/目标/超期结算（track_record/job.py + scheduler 切换），幂等 + 失败可重试

## 3. 全量记录与 API

- [x] 3.1 `_persist_decision_log` 改为写 predictions：reject/hold/watch/neutral 同样落库，rationale_snapshot 冻结，action→direction 映射，旁路失败不阻断
- [x] 3.2 `/api/v1/track-record` 只读端点：overview（指标 + as_of + disclaimer + 显著性门槛）+ predictions 列表（默认全部状态，分页上限 50，不可隐藏 loss）

## 4. 前端战绩页

- [x] 4.1 战绩页接 track-record API：总览区 + 观点日志合并单页，状态标签分色，进行中观点标「未结算」
- [x] 4.2 固定风险提示（不可关闭）、空态/样本不足（「样本积累中」进度，不显示 0 冒充）
- [x] 4.3 `/decisions` 旧战绩页重定向到 track-record 视图（TrackRecordPage 取代 DecisionCenter 接入）

## 5. 验收门禁（交互类变更）

- [x] 5.1 E2E spec 覆盖核心场景：战绩页渲染（总览+日志）、样本不足空态、风险提示可见、/decisions 重定向
- [x] 5.2 E2E 门禁全绿（`cd tests/e2e/playwright && npx playwright test tests/decisions.spec.ts --workers=1`，3 例）
- [x] 5.3 `uv run pytest`（门禁 `-m "not live"`）与 `cd frontend && npm test` 全绿
- [x] 5.4 判定引擎验收用例对照设计档案 §7（胜率口径、中性带、superseded、冻结不可改、样本量门槛）
- [x] 5.5 人工验证报告落 `tests/validation/2026-09-03-add-track-record-validation.md`（待人工抽查项已明列）
- [x] 5.6 sync 顺序确认已记录：decision-outcome-tracking 先归档，本 delta MODIFIED 再应用（见 design.md）
