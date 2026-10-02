# Proposal: update-decision-price-gate

## Why

2026-09-30 归档的 update-decision-integrity-gates 将决策文本价位交叉校验落地为**纯观测**（spec 明写「校验 SHALL NOT 硬中断管线……可观测优先」）。2026q3 首个正式批的回归评审（2026-10-02）实证该设计的缺陷：校验器抓到真错误（决策文本价位 95 vs 已验证近期低点 570，偏差 83.33%），管线却把报警文本原样渲染进最终报告并放行 Fund Manager 审批——校验器从门禁降级为批注，报告带病交付。

## What Changes

- **校验处置升级为门禁**（MODIFIED price-level-tooling）：`decision_price_check` 登记的 anomaly 不再仅渲染旁注——risk_judge 携 anomaly 明细与已验证值**定向打回重试一次**；重试后修正 → 放行进 FM 审批；仍异常 → **阻断**（不进审批、不产出报告）。
- **报警退出交付物**：移除报告「价位待核实」旁注渲染（`_price_anomaly_notes`），anomaly 明细仅落 state/Langfuse trace。
- **阻断终态可见化**（ADDED pipeline-events）：管线正常结束但未产出报告时，会话 SHALL 置 failed 并持久化 failure_reason、下发 SSE error 终态事件——不再停留 running 等超时兜底（顺带修复勾稽校验 FAIL → END 既有悬挂缺口）。
- **故障注入回归测试**：复现「95 vs 570」场景（stub LLM 固定输出错误价位），断言门禁真阻断（FM 未达、无报告、会话 failed）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `price-level-tooling`: 「决策文本价位与已验证技术指标交叉校验」的处置语义从「纯观测 + 报告旁注」改为「打回重试一次 → 仍异常阻断交付；报警仅进 trace 不进报告」
- `pipeline-events`: 新增「管线阻断终态可见化」要求——管线正常结束但无报告（门禁阻断/勾稽 FAIL）时 MUST NOT 停留 running

## Impact

- `src/finance_agent/nodes/risk.py`：risk_judge 增加第 4 个打回回路（价位交叉校验），产出 gate 结果
- `src/finance_agent/routing.py` + `src/finance_agent/graph.py`：`risk_judge → fund_manager` 无条件边改为条件路由（gate fail → END）
- `src/finance_agent/state.py`：新增 `decision_price_gate` 字段
- `src/finance_agent/nodes/report.py`：移除 `_price_anomaly_notes` 渲染链路
- `src/finance_agent/nodes/fund_manager.py`：`FINAL_CHECK_LABELS` 接入 gate（FM 可见「打回后已修正」复核性标注）
- `src/finance_agent/api.py`：`_run_graph_streaming` 收尾处理——无报告即置 failed + SSE error 事件
- `src/finance_agent/agent_factory.py`：`run_deep_analysis` 工具正常结束分支按 `final_report` 分流——无报告同语义置 failed + 阻断 TOOL_RESULT（ReAct 慢路径与 fast path 收口一致）
- 测试：`tests/metrics/test_decision_price_check.py`、`tests/nodes/test_risk.py`、`tests/nodes/test_report_decision_render.py`、`tests/nodes/test_fund_manager.py`、`tests/test_graph_5layer.py`、`tests/test_api_failure_reason.py` 增改
- **非交互类变更**（纯后端逻辑 + 会话终态；SSE error 事件为既有类型，前端无改动）→ 不适用 E2E 门禁与人工验证环节
