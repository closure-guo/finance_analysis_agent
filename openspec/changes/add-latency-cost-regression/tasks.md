# Tasks: add-latency-cost-regression

## 1. 度量采集

- [ ] 1.1 失败测试先行：聚合口径与基线对比
- [ ] 1.2 Langfuse trace 聚合（时延分解/token/成本），模型单价表配置化

## 2. 基线与门禁

- [ ] 2.1 性能基线档案落 docs/evals/（仿 v3 delta 归档）
- [ ] 2.2 超基线阈值告警/失败（阈值配置化）

## 3. 趋势

- [ ] 3.1 nightly 时序沉淀 + 单调劣化趋势告警

## 4. 验证

- [ ] 4.1 uv run pytest / ruff / mypy 全绿
- [ ] 4.2 首轮基线采集并归档
