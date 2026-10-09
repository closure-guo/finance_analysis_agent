# Delta for agent-evaluation-suite

## ADDED Requirements

### Requirement: 故障注入回归集

系统 SHALL 维护故障注入回归集 `tests/regression/fault_injection/`：每条样本为一次已修复的真实故障（标注故障来源版本与修复 PR），配确定性断言——对应守卫 SHALL 拒绝该样本。首批样本 SHALL 覆盖三类：F1 推理泄露（英文残留/思考文本/截断进成稿，守卫为 `llm-output-contract` 的 validate_deliverable_text）、F2 报警外露（价位校验报警文案泄入报告成稿，守卫为渲染链不接收 anomalies）、F3 期次错位/同值撞车（citation 消歧校验）。回归集 SHALL 以 pytest marker `fault_regression` 组织并在 CI 独立步骤运行，全程零 token、确定性。守卫行为被削弱（放宽泄露模式、渲染链重新接收 anomalies、消歧校验关闭）时对应样本 SHALL 变红。

#### Scenario: 泄露样本被守卫拒绝

- **GIVEN** tests/regression/fault_injection/ 下 F1 泄露样本（含英文残留、思考前缀、句中截断三类）
- **WHEN** 运行 `pytest -m fault_regression`
- **THEN** validate_deliverable_text 对全部样本返回拒收 verdict，测试绿

#### Scenario: 报警外露护栏

- **GIVEN** 构造 state 含 decision_price_anomalies（价位报警文案）
- **WHEN** 执行报告渲染
- **THEN** 成稿不含报警文案，断言绿；若渲染链改为接收 anomalies 则本样本红

#### Scenario: 撞车样本被消歧校验拦截

- **GIVEN** 41.69% 年报/单季撞车 claim 样本（interpretation 期次标记与 field_ref 错配）
- **WHEN** 执行 citation 校验
- **THEN** FAIL 且桶为 semantic_period_mismatch

#### Scenario: CI 门禁

- **WHEN** CI 流水线运行
- **THEN** fault_regression 步骤独立执行且必须全绿，失败阻断合并
