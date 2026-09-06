# add-track-record-stage-b 验证报告

- 日期：2026-09-04
- 提交：12af347（盯市/净值/风险指标引擎 + 战绩页风险卡与净值图）

## 自动化验证

- 全套后端 pytest：1833 passed（stage-b 新增 22 例：三表 DDL 幂等、盯市 upsert、
  等权组合收益、指标引擎（年化/波动/夏普/回撤/风险分）、FakeClient 盯市批、
  净值持久化、scheduler 双任务注册）
- 前端 vitest：474 passed（风险卡渲染/空态/曲线渲染 4 例新增）
- E2E 门禁（CI 镜像，无 key）：19 passed / 7 skipped——decisions.spec 扩展
  断言「无快照 → risk-empty 展示、曲线不渲染」
- ruff / mypy 全绿；openspec validate --strict 通过

## 已实现行为核对

- daily_marks 幂等（(prediction_id, mark_date) 覆盖）；缺数据容错（跳过该观点）
- 双净值线以首个盯市日归一 1.0；数据缺口断点不插值（spec 数据缺口不伪造）
- 风险分 clip(round(0.6*dd%+0.4*vol%),1,10)；力鼎光电观测案例（41.2%/75.6%）→ 10 ✓
- 时序：settle 16:00 → daily-marking 16:30 → metrics-snapshot 16:35

## 待人工验证（需真实交易日收盘数据）

1. 真实行情下的盯市/净值落地：下个交易日收盘后访问 /track-record 确认风险卡与
   净值曲线出现真实数据（当前 30 条历史 predictions 均为 unresolvable，无 open
   观点可盯市——需新产生观点后观察）
2. 日批与 settle 的先后关系在生产环境抽查（scheduler 日志）
