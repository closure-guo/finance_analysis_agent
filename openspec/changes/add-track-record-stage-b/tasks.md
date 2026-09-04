# Tasks: add-track-record-stage-b

## 1. 数据层

- [ ] 1.1 三张新表 DDL（daily_marks / equity_curve / agent_metrics_daily）+ 迁移幂等
- [ ] 1.2 失败测试先行：盯市写入、空仓日记 0、同日重跑幂等

## 2. 指标引擎

- [ ] 2.1 盯市模块（缺数据容错）
- [ ] 2.2 净值曲线计算（等权 1/N 日再平衡）
- [ ] 2.3 指标引擎（年化/波动/夏普/回撤/风险分，无风险利率与映射表配置化）
- [ ] 2.4 后台任务 daily-marking + metrics-snapshot 挂 APScheduler

## 3. API 与前端

- [ ] 3.1 总览 API 扩展组合指标字段
- [ ] 3.2 战绩页净值曲线（ECharts）+ 风险卡
- [ ] 3.3 E2E：战绩页风险维度展示

## 4. 验证

- [ ] 4.1 uv run pytest / ruff / mypy 全绿
- [ ] 4.2 人工验证报告落 tests/validation/
