# Tasks: update-decision-price-gate

- [x] risk_judge 价位交叉校验打回回路：anomaly 非空 → 携明细打回重试一次 → 重放 payout self-check → 复检；gate 结果（pass/fail + note）落 `decision_price_gate`，残留 anomaly 落 `decision_price_anomalies`（故障注入用例：95 vs 570 修正放行 / 仍异常 fail 两形态）
- [x] 路由与图接线：`after_risk_judge` 条件路由（gate fail → END），`risk_judge → fund_manager` 改条件边；gate fail 路径下 fund_manager/generate_report 不执行
- [x] 报警退出交付物：移除 `_price_anomaly_notes` 及报告侧 anomalies 渲染链；`FINAL_CHECK_LABELS` 接入 gate（FM 可见「打回后已修正」，报告不渲染任何报警文本）
- [x] 阻断终态可见化：`_run_graph_streaming` 无报告收尾 → 会话置 failed + failure_reason（含阻断来源）+ SSE error 事件；勾稽 FAIL 路径同款收尾；正常完成路径不受影响
  - [x] ReAct 慢路径（agent_factory run_deep_analysis）同语义收口：正常结束分支按 `final_report` 分流——无报告置 failed + 归因 + 阻断 TOOL_RESULT（带 pipeline_blocked 标记、不带 report_ready），跳过报告落库与决策落战绩
- [x] state 声明与既有测试回归：`decision_price_gate` 声明、`decision_price_anomalies` 注释修订；test_graph_5layer 节点产出通道门禁通过；受影响既有测试（test_report_decision_render / test_fund_manager / test_risk / test_decision_price_check）全绿
- [x] 全量验证：`uv run ruff check`、`uv run mypy`、`uv run pytest`（全量）通过；验证证据落 tests/validation/（2026-10-02-update-decision-price-gate-validation.md：ruff 干净、mypy 零新增 81≡81、pytest 3916 passed / 1 failed @live 既有环境项 / 7 skipped）
