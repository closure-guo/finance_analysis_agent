# 验证报告: update-decision-price-gate

**日期**: 2026-10-02
**分支**: `update-decision-price-gate`（commits b17b70c6 → T5 收尾提交）
**关联 delta**: openspec/changes/update-decision-price-gate/（price-level-tooling MODIFIED + pipeline-events ADDED）
**变更类型**: 非交互类（纯后端逻辑 + 会话终态；SSE error 事件为既有类型、前端零改动）→ 不适用 E2E 门禁
**执行方式**: subagent-driven-development（每任务 implementer + 独立 task-reviewer 审查，全部通过）

## 变更内容

决策文本价位交叉校验（update-decision-integrity-gates 落地的纯观测层）升级为**门禁**：anomaly 非空 → risk_judge 携明细（source_text 四要素）定向打回重试恰一次 → 修正放行进 FM 审批（note「打回后已修正」）；仍异常 → `after_risk_judge` 路由阻断（不进审批、不产出报告）。报告渲染链移除「价位待核实」标注（报警仅进 state/Langfuse trace）。管线无报告正常结束时（门禁阻断 / 勾稽 FAIL）会话置 failed + failure_reason，fast path 下发 SSE error、ReAct 慢路径下发阻断 TOOL_RESULT——不再停留 running 等超时兜底。

## 验证结果

| 验证项 | 证据位置 | 结果 |
|---|---|---|
| 故障注入：偏差 anomaly（95 vs 570）打回后修正放行 | `tests/nodes/test_risk.py::TestDecisionPriceGate::test_anomaly_retry_fixed_passes`（LLM 恰 2 次调用、gate pass「打回后已修正」、残留清空、终稿含 570） | ✅ |
| 故障注入：打回后仍输出错误价位 → gate fail | `tests/nodes/test_risk.py::TestDecisionPriceGate::test_anomaly_persists_after_retry_fails_gate`（note「已打回仍未通过：1 条残留」） | ✅ |
| 门禁路由阻断（不进 FM / 不出报告） | `tests/test_after_risk_judge_routing.py` 4 用例（fail→`__end__`、pass/缺失/形态噪声→`fund_manager`、图接线判别力经突变校验） | ✅ |
| 打回反馈四要素（source_text 补齐） | `tests/nodes/test_risk.py::test_price_retry_feedback_includes_source_text` | ✅ |
| 重试换代后兄弟结论复核（I-1 链） | `tests/nodes/test_risk.py`（sell→watch 缺理由如实改注用例） | ✅ |
| 校验器自身异常 fail-open | `tests/nodes/test_risk.py::TestDecisionPriceGate::test_validator_crash_fails_open` | ✅ |
| 报警不渲染进报告（渲染链签名锁） | `tests/nodes/test_report_decision_render.py::TestPriceAlarmNeverRendered`（`_price_anomaly_notes` 零残留、签名不含 anomalies） | ✅ |
| gate 复核注不泄报告「结构不完整」块 | `tests/nodes/test_report_decision_render.py::TestGateRecheckNoteNeverLeaksReport`（含敏感性对照用例） | ✅ |
| 阻断终态 fast path（会话 failed + failure_reason + SSE error + 无报告/无 decision_log） | `tests/test_api_blocked_terminal.py`（fake graph 端到端 5 用例） | ✅ |
| 阻断终态 ReAct 慢路径（failed + 阻断 TOOL_RESULT、不落战绩） | `tests/test_agent_factory_blocked_terminal.py` 3 用例（红态经审查方独立突变复现：父版本恰红于 `completed==failed` 断言） | ✅ |
| 正常完成路径不受影响 | `tests/test_api_blocked_terminal.py::test_normal_completion_not_affected` + `test_agent_factory_blocked_terminal.py::test_normal_completion_not_affected` | ✅ |
| 勾稽 FAIL 归因映射 | `tests/test_api_blocked_terminal.py::TestBlockedFailureReason::test_validation_fail_maps_to_validate_node` | ✅ |

## 门禁命令（全量，本 worktree 实测）

| 命令 | 结果 |
|---|---|
| `uv run ruff check` | All checks passed! |
| `uv run mypy src/finance_agent` | 分支 81 errors in 20 files ≡ main 基线 81 errors in 20 files（**零新增**；api.py 既有错误行号平移 1223→1257 / 1924→1958 与插入代码行数吻合，错误类型不变） |
| `uv run pytest`（全量） | **3916 passed, 1 failed, 7 skipped**（676s）。唯一失败 `tests/evals/test_fm_decision_live.py::test_fm_decision_live_report` 为 @live nightly 用例：环境密钥上溯（api.py 顶层 `load_dotenv()` 父目录遍历）致其在无 LLM 密钥环境误运行——本分支 diff 未触碰该文件及其 import 链（`git diff --name-only main` 核对），Task 1 时已在基线确认同态（复跑为 skip），非本变更回归 |

## 逐任务审查记录

| 任务 | commit | 审查结论 |
|---|---|---|
| T1 risk_judge 门禁回路 + state 声明 | b17b70c6 | Spec ✅ / Approved（3 Minor 已于 T2 收口） |
| T2 after_risk_judge 路由 + 图接线 | 5b4486a1 + 33edbdb3 | Spec ✅ / Approved（langgraph 1.2 显式 path_map 偏离经实证裁决为必要且语义等价） |
| T3 报警退出交付物 | 65b7ad0e | Spec ✅ / Approved（2 Minor 已于 T4 收口） |
| T4 阻断终态可见化（API） | ede0ddad + 1a423d27 | Spec ✅ / Approved（审查揪出 change 级缺口→修复轮） |
| T4 修复轮 ReAct 慢路径收口 | 788d504f | Spec ✅ / Approved（红态独立复现） |
| T5 全量验证 + 工件入库 | 本提交 | 见上表 |

## 遗留（已挂 issue 跟踪）

- #188 决策 schema 按 action 分型（exit vs short 模板分离）——评审 P1
- #189 辩论/摘要层论据新鲜度同步——评审 P1
- #190 同指标多口径映射说明——评审 P2
- #191 中报毛利率口径人工对账——评审 P2
- 阻断分支 Langfuse trace→session 关联缺失（T4 修复轮 Minor，失败运行反馈回溯增强，非门禁语义）
- `test_fm_decision_live` 受 `load_dotenv()` 上溯误运行的收口（与本变更无关的既有问题）

## 结论

[x] 全部通过——门禁三态（修正放行 / 仍异常阻断 / fail-open）+ 阻断终态两条路径（fast path / ReAct）均有故障注入回归锁；可进入 archive 流程
