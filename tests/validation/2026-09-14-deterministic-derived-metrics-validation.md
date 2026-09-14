# deterministic-derived-metrics 人工验证报告（2026-09-14）

## 验证范围

delta 目标：止损距离/赔率由 validate 节点纯规则计算（不再让 LLM 心算），经 state 注入风险辩论三方与 risk_judge context，标注「直接引用，不得重算」。

## 已验证项

### 1. 计算逻辑（单元测试，tests/nodes/test_validate_trade_prices.py::TestDerivedMetrics，6 测试）

- buy 方案 pass：entry 52.0 / stop 47.8 / target 60.0 → 止损距离 8.08%、赔率 1.90:1（reward=t-e / risk=e-s），与手算一致
- corrected 路径：按修正后价位计算
- fail 打回路径：不计算
- 边界：stop==entry、stop/target 为 0 或缺失 → 派生值 None + missing_reason，无 0/无穷占位

### 2. 注入逻辑（单元测试，tests/nodes/test_risk.py::TestDerivedMetricsInjection，3 测试）

- watch/hold：不注入派生指标行
- buy：三方辩论 context 与 risk_judge context 均含同一行「派生指标（代码计算）: 止损距离 X%、赔率 Y:1:（算术已由代码完成，直接引用，MUST NOT 自行重算或改写）」
- 两值任一为 None：不注入（空值不注入）
- reasoning 自算值与代码值冲突时，context/下游取代码值

### 3. state 通道（incident 027 修复实证，E2E 3 次真实运行）

- `derived_metrics` 键已在 AnalysisState 声明，图合并不再静默丢弃（tests/nodes/test_validate_trade_prices.py::TestStateChannelsDeclared 契约测试锁定 `build_5layer_graph().builder.channels`）
- 3 次真实运行（tests/scripts/verify_deltas_e2e.py，记录见 delta-e2e-验证记录.md）：price_check 家族持久化、watch 分支渲染、buy+null 价位分支「未提供」渲染均验证通过

### 4. 真实运行行为（round8/round9 实验，18 条 deep trace）

- 全部决策价位为 null（trader 未申报数值价位，0/4 轮）→ 派生指标 None+missing_reason → context 不注入——**空值不注入逻辑经真实数据验证**，无假数字进入辩论
- prompt 已 deploy（risk_debater.md / risk_judge.md 来源说明行，14 导入）

## 未验证项（如实声明）

- **buy+真实数值价位路径**：计算与注入逻辑仅有单元测试覆盖，真实报告中的端到端形态（辩论引用代码值、报告渲染同源）未触发——阻塞原因是 trader 连续 4 轮不申报数值价位（round9 宁德 buy 决策 entry/stop/target 仍全 null，止损仅散文描述）。已登记 metrics.md：价位必填化建议升级为独立 delta，落地后补核本路径。

## 结论

可验证范围内全部通过：计算/注入/边界/state 通道/空值路径均有测试或真实运行证据。残余风险（buy+真实价位端到端）已显式记录并挂接价位必填化 delta，不阻塞归档——该路径的代码行为由 6+3 个单元测试锁定，缺失的只是真实数据触发。
