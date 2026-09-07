# Tasks: calibrate-fm-approval

## 1. 取证（已完成）

- [x] 1.1 从 Langfuse trace + 战绩库统计 FM 决策历史分布，定位根因
- [x] 1.2 结论：approve 53% 行为健康；真实缺陷 = return 回路反馈断裂（trader 重跑无 FM 退回理由）；风控否决合理，不得放松（结论已写入 proposal.md）

## 2. return 回路修复（trader 反馈注入）

- [x] 2.1 失败测试先行：trader context 在 return 重跑时包含 fund_manager_decision_reasoning；approve/reject 时不注入
- [x] 2.2 `trader.py::_build_trader_context` 注入「基金经理退回意见」段落
- [x] 2.3 回路契约测试：fund_manager 节点 return 时 reasoning 落 state（test_fund_manager.py）+ trader 读取（test_trader.py）闭合

## 3. 评估接入（evals/fm_decision）

- [x] 3.1 失败测试先行：分布聚合与门禁断言（fixtures 离线路径，tests/evals/test_fm_decision.py）
- [x] 3.2 Langfuse trace 拉取（run.py）+ approve/return/reject 分布报告（按日分桶、无 trace 报样本不足）
- [x] 3.3 风控否决召回门禁（高风险样本 approve 即失败，fixtures 对抗样本集驱动）
- [x] 3.4 否决理由完整门禁（decision 必须带 reasoning，live 数据直接断言）

## 4. 验证

- [x] 4.1 uv run pytest（全套 1811 passed）/ ruff / mypy 全绿
- [x] 4.2 nightly @live 注册：tests/evals/test_fm_decision_live.py（pytest -m live，无 key 跳过；nightly CI 需加 LANGFUSE secrets 才能全量生效——仓库管理员跟进）
- [ ] 4.3 真实链路人工验证：deep 分析走通 return→trader 重跑→报告反映改进方案（Langfuse trace 佐证）