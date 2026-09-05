# Tasks: add-track-record-stage-b

## 1. 数据层

- [x] 1.1 三张新表 DDL（daily_marks / equity_curve / agent_metrics_daily）+ 迁移幂等
- [x] 1.2 失败测试先行：盯市写入、空仓日记 0、同日重跑幂等

## 2. 指标引擎

- [x] 2.1 盯市模块（缺数据容错：停牌/接口失败仅跳过该观点）
- [x] 2.2 净值曲线计算（等权 1/N 日再平衡，agent/基准双线首个盯市日归一 1.0）
- [x] 2.3 指标引擎（年化/波动/夏普/回撤/风险分，无风险利率 TRACK_RISK_FREE_RATE 与 RISK_LABELS 映射表配置化）
- [x] 2.4 后台任务 daily-marking（16:30）+ metrics-snapshot（16:35）挂 APScheduler

## 3. API 与前端

- [x] 3.1 总览 API 扩展 portfolio 组合指标块（available=false 时字段 null）
- [x] 3.2 技录页风险卡（年化/波动/夏普/回撤/风险分+标签）+ 净值曲线（ECharts，agent vs 沪深300）
- [x] 3.3 E2E：战绩页兜底空态（risk-empty 展示、曲线不渲染）+ 门禁回归

## 4. 验证

- [x] 4.1 uv run pytest（全套 1833 passed）/ ruff / mypy 全绿
- [x] 4.2 前端 vitest 474 passed；E2E 门禁 19 passed / 7 skipped（CI 镜像环境）
- [x] 4.3 人工验证：真实行情跑通每日盯市并落地净值（下个交易日收盘后查 /track-record 曲线）；日批时序与 settle 的先后关系人工抽查（2026-09-05：真实 akshare 行情实测，marked=21/equity_points=10，曲线+风险指标+切片渲染正常；时序 settle 16:00 → marking 16:30 核对 scheduler 注册顺序，报告 tests/validation/2026-09-05-track-record-stage-b-validation-2.md）