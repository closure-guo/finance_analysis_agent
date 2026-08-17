# 人工验证报告: add-llm-provider-gateway

**日期**: 2026-08-16
**delta**: openspec/changes/add-llm-provider-gateway/
**E2E 门禁**: 交互类（api /api/llm-config/test 升级 + gateway 主链路）适用

## 验证矩阵

| 验证项 | 依据 | 结果 |
|---|---|---|
| gateway 单测 | `tests/llm/`（types/registry/resolver/adapter/contracts/probes/gateway/action_protocol/errors）90 用例 | ✅ 全绿 |
| 全量回归 | `pytest -k "not live"` | ✅ 989 passed |
| lint/mypy | ruff / mypy（12 源文件） | ✅ 干净 |
| grep 门禁 | adapters 外禁 import litellm | ✅ 通过（legacy/harness 存量 allowlist，5.1 收紧） |
| ReAct loop action 集成 | `test_react_loop`（DSML 不回归 + action 集成） | ✅ 9 passed |
| judge 输入合同 | `tests/evals/test_judges.py`（input_missing 不评分） | ✅ 15 passed |
| 端到端评估跑批 | `python -m evals.run baseline-v2-ark --local` | ⬜ 见附录（后台跑批） |

## 结论

[ ] 全部通过，可 archive — 须待端到端跑批结果 + 5.1 薄壳转调收口
[x] 待确认项：
1. **5.1 薄壳转调**（legacy/harness → gateway 完整流转调 + 门禁收窄）未完成——
   涉及生产主链路（quick/follow_up）大改，需独立验证轮 + 真实调用对拍
2. **4.2 前端设置页能力矩阵展示** 未实现（仅后端端点升级返回 capability 矩阵；
   前端消费为增量）
3. 端到端评估跑批（后台执行中）结果待核对（judge_failures=0 + 四 rubric 不回退）
4. @live 合同探测（tests/llm_contracts）需 nightly 跑真实方舟验证防漂移

## 人工核对要点（未完成项的交接清单）

- 5.1 前：gateway.complete_text 为骨架（非流式），complete_stream/with_tools 未实现；
  legacy.call_llm_stream/with_tools 仍是主链路，勿误删
- 门禁 allowlist 当前含 `llm/legacy.py`、`harness/litellm_client.py`（Task 5.1 后移除）
- 端到端对拍基线：r6（debate_quality=4.0、decision_grounding=2.86、judge_failures=0）
