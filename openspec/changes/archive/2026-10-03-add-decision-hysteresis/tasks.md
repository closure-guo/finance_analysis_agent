# Tasks: add-decision-hysteresis

- [x] 均衡带判定：RM 中性评级判据 + state 键 + 均衡带内执行动作无增量的打回重申与降级（TDD：无增量降级 / 携增量放行 / 非均衡带不受影响）
- [x] 方向滞回：predictions 只读近窗查询 + 历史注入 context + 翻转增量申报复核 + 维持前判降级（TDD：无增量滞回 / 携增量放行 / 窗口外不生效 / buy↔sell 从严）
- [x] prompt 契约：risk_judge 增量申报段 + deploy_prompts 同步 + agent-prompt-contracts 契约更新
- [x] pass@k 型稳定性回归：单元级 stub 双跑路径已锁（TestDecisionHysteresis）；@live nightly 观察复用既有 live 基建部署后进行（取舍记录见 validation 报告）
- [x] 全量验证 + 验证报告 + 均衡带/滞回阈值校准记录（docs/evals）
