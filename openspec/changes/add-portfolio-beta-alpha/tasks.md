# Tasks: add-portfolio-beta-alpha

## 1. 指标引擎 β/α 计算

- [x] 1.1 metrics.py:日收益对推导(首日剔除/双非空取交集)+ OLS β + 年化 Jensen α + 20 对样本门槛(TDD:正常回归/精确构造 β/样本不足 null/无基准序列 null)
- [x] 1.2 model.py:agent_metrics_daily 幂等加列迁移 + 快照/读取带 beta/jensen_alpha(TDD:旧库迁移/写入读回)

## 2. API 与前端

- [x] 2.1 overview 端点 portfolio 块新增两字段 + 集成测试
- [x] 2.2 战绩页指标区两格(格式/副标题/置空)+ 前端单测
- [x] 2.3 E2E:track-record 专属套件新增 spec(seed 造 ≥20 点相关序列 → 断言两格数值;样本不足 → "—")

## 3. 验证收口

- [x] 3.1 ruff + mypy(零新增)+ 后端全量 pytest + 前端 npm test
- [x] 3.2 E2E 三套件绿;人工验证报告落 tests/validation/
