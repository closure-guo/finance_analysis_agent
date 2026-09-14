# 027: 价位校验回路 state 键未声明——fail 打回与价位修正在真实图从未生效（2026-09-13）

## 症状

round7 校准后的 delta 端到端验证（`tests/scripts/verify_deltas_e2e.py`）发现：两条真实 trace 的终态中 `price_check` 与新键 `derived_metrics` 均为 None/缺失——validate 节点明明返回了这些键。

## 根因

`AnalysisState`（`state.py`，`TypedDict(total=False)`）未声明 `price_check` / `price_check_feedback` / `price_check_attempts` / `price_level_corrected` / `price_level_correction_reason`（及其后补的 `derived_metrics` / `citation_coverage_gap` / `value_mismatch_repaired`）。LangGraph 图合并**静默丢弃未声明键**——这一行为项目此前已在 FM 键处踩过并注释（「未声明则被图合并丢弃」），但 validate 家族与 citation 家族的键漏补。

**影响面（r1–r7 全部实验）**：

1. `after_validate_trade_prices` 路由恒读到空 dict → **fail 打回 trader 的重试从未触发**，首次校验失败的方案原样放行进入风险辩论；
2. 二次失败走参考带修正的路径不可达（`price_check_attempts` 恒被丢为 0 以下语义）→ **「价位修正」机制从未在真实图生效**，报告的「价位修正」行从未出现；
3. 单元测试全绿：各测试直接以 dict 调用节点函数，绕过图合并——与 FM 盲审批（incident 前身，1.14）同一模式：**节点测试覆盖不了图合并契约**。

判定为「真错误」桶（机制性缺陷，非数据问题）：修复方式为补声明，不涉及 prompt/数据。

## 修复

- `state.py` AnalysisState 补声明 8 键（price_check 家族 5 + derived_metrics 1 + citation_coverage_gap / value_mismatch_repaired 2，后者由同次键审计发现）；
- 图通道契约测试锁死（`tests/nodes/test_validate_trade_prices.py::TestStateChannelsDeclared`：断言 `build_5layer_graph().builder.channels` 含全部键）；
- 全量节点测试 277 绿。

## 附带发现

- 审计同时发现 `deterministic-derived-metrics` delta 的 `derived_metrics` 若非本次 E2E 验证也会带病上线（写入即被丢弃）——**端到端验证的必要性实证**；
- citation_node 的 `markdown`/`claims` 顶层键为 helper 函数返回，非节点返回，不涉状态（误报排除记录）。

## 预防

- 图通道契约测试已固化；后续新增 state 键的 delta，tasks 中 MUST 包含「AnalysisState 声明 + 通道契约测试」步骤。
