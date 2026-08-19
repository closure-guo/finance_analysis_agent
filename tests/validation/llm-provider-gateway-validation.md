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

## B2 轮次（2026-08-19，feat/llm-gateway-51：call_llm_stream 薄壳转调）

| 验证项 | 依据 | 结果 |
|---|---|---|
| provider_options 机制（§7.1） | `tests/llm/test_provider_options.py`（registry 三件套 + resolver 三层合并 + 白名单拒绝） | ✅ 全绿 |
| adapter 消费 + timeout 注入 | `tests/llm/adapters/test_apply_provider_options.py` + gateway temperature 用例 | ✅ 全绿 |
| 薄壳双路径对拍 | `tests/llm/test_llm_stream_thinshell.py`（tuple 流 == CanonicalEvent 流拼接；error→重抛 LLMError retryable；DeprecationWarning；半套配置拒绝） | ✅ 全绿 |
| 受影响测试迁移 | `tests/test_llm.py` 3 个 stream 测试 + `test_pipeline_llm_config.py`（mock 目标 → `adapters.litellm_adapter.raw_stream`，断言零弱化） | ✅ 全绿 |
| 全量回归 | `uv run pytest -k "not live"` | ✅ 1026 passed（基线 992 + 新增） |
| lint / 类型 | ruff 全过；mypy 69 错误集与基线 027121f 逐行一致（零新增） | ✅ |
| grep 门禁 | legacy.py 仍在 allowlist（call_llm/call_llm_with_tools 未转调，计划内） | ✅ 通过 |
| 真实 quick 验证 | 方舟 GLM（openai/glm-5.3）真实流式：`call_llm_stream(quick=True)` | ✅ 171 thinking 分片(702字) + 完整 answer（「A股T+1…」） |

已知边界（B2 计划内）：薄壳对 messages 含 tool 角色不再强制 disable_thinking（task C 域）；半套请求配置经 resolver 显式拒绝（spec「半套请求配置被拒绝」），1 个旧测试随迁为完整配置。

## 结论

[ ] 全部通过，可 archive — 须待端到端跑批结果 + 5.1 薄壳转调收口
[x] 待确认项：
1. **5.1 薄壳转调**：A（complete_stream Canonical 对接）+ B1（Langfuse 观测收口）已完成；
   剩 B2（`call_llm_streaming` 转调，牵动全部管线节点调用 + 受影响测试迁移 mock 目标 + 双路径对拍）
   与 C（harness loop → CanonicalEvent），需独立验证轮 + 真实 quick 调用对拍
2. **4.2 前端设置页能力矩阵展示** 未实现（仅后端端点升级返回 capability 矩阵；
   前端消费为增量）
3. 端到端评估跑批（后台执行中）结果待核对（judge_failures=0 + 四 rubric 不回退）
4. @live 合同探测（tests/llm_contracts）需 nightly 跑真实方舟验证防漂移

## 人工核对要点（未完成项的交接清单）

- 5.1 前：gateway.complete_text 为骨架（非流式），complete_stream/with_tools 未实现；
  legacy.call_llm_stream/with_tools 仍是主链路，勿误删
- 门禁 allowlist 当前含 `llm/legacy.py`、`harness/litellm_client.py`（Task 5.1 后移除）
- 端到端对拍基线：r6（debate_quality=4.0、decision_grounding=2.86、judge_failures=0）
