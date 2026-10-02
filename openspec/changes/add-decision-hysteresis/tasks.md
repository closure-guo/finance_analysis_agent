# Tasks: add-decision-hysteresis

- [ ] 均衡带判定：RM 中性评级判据 + state 键 + 均衡带内执行动作无增量的打回重申与降级（TDD：无增量降级 / 携增量放行 / 非均衡带不受影响）
- [ ] 方向滞回：predictions 只读近窗查询 + 历史注入 context + 翻转增量申报复核 + 维持前判降级（TDD：无增量滞回 / 携增量放行 / 窗口外不生效 / buy↔sell 从严）
- [ ] prompt 契约：risk_judge 增量申报段 + deploy_prompts 同步 + agent-prompt-contracts 契约更新
- [ ] pass@k 型稳定性回归（@live nightly：同输入 5 跑方向一致性 ≥4/5 预期——滞回吸收采样翻转）
- [ ] 全量验证 + 验证报告 + 均衡带/滞回阈值校准记录（docs/evals）
