# Tasks: add-fault-injection-regression-set

- [ ] `tests/regression/fault_injection/` 目录 + F1 泄露样本语料（拓荆 v5 171013 实测片段 + 英文残留/截断变体），断言 validate_deliverable_text 全拒
- [ ] F2 报警外露护栏样本：带 decision_price_anomalies 的 state 渲染成稿不含报警文案
- [ ] F3 撞车样本：41.69% 期次标记错配 claim，断言 semantic_period_mismatch（依赖 add-period-key-citation-validation）
- [ ] pyproject.toml 注册 marker `fault_regression` + CI 独立步骤（零 token）
- [ ] 回归集 README：运行方式 + 每样本故障来源（版本/修复 PR）
