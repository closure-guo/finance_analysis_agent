# Tasks: deterministic-derived-metrics

## 1. 前置确认

- [ ] 1.1 确认 `harden-decision-report-semantics` 已归档；未归档则实现任务挂起（纯文档/规范任务不受限）
- [ ] 1.2 与 round8 材料版本变更合并排期：本 delta 改变风险辩论 context，单独成一个实验变量，不得与其他 judge 输入变更混入同一轮

## 2. 测试先行

- [ ] 2.1 validate 测试：buy 方案 pass 时 state 携带止损距离 8.08%/赔率 1.90:1（entry 52.0/stop 47.8/target 60.0）
- [ ] 2.2 validate 测试：corrected 路径用修正后价位计算；fail 打回路径不计算
- [ ] 2.3 validate 测试：stop==entry 或 stop/target 为 0/缺失时派生值为 None 且注明原因，无 0/无穷占位
- [ ] 2.4 risk 测试：watch/hold 不注入派生指标行；buy 时三方 context 含同一行；risk_judge context 同
- [ ] 2.5 测试：reasoning 自算值与代码值冲突时，context/下游取代码值

## 3. 实现

- [ ] 3.1 `nodes/validate.py`：pass/corrected 后计算派生指标写 state（除零/缺失 → None+原因），纯规则无 LLM
- [ ] 3.2 `nodes/risk.py`：辩论三方与 risk_judge context 注入「派生指标（代码计算）：…」行（空值不注入）
- [ ] 3.3 风险辩论与 risk_judge prompt 各补一句来源说明（算术已由代码完成，直接引用不得重算改写）

## 4. 发布与验证

- [ ] 4.1 `uv run python scripts/deploy_prompts.py` 发布 prompt（eval 门禁依赖）
- [ ] 4.2 `uv run pytest` 全量绿 + `uv run ruff check` + `uv run mypy`
- [ ] 4.3 端到端跑一次真实分析（buy 方案），核对：辩论各方引用的赔率一致且等于代码值、报告渲染值同源（交互类变更人工验证环节）
- [ ] 4.4 人工验证报告落 `tests/validation/`
- [ ] 4.5 tasks 全勾后 `openspec archive`，spec sync 合入主规范 `openspec/specs/derived-risk-metrics/`
