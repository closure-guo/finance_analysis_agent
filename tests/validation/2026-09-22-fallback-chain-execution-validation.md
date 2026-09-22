# 人工验证报告: fallback 链执行接线（llm-policy-router Requirement 2）

**日期**: 2026-09-22
**验证人**: Closure（agent 执行，人工抽查项见下）
**关联规范**: `openspec/specs/llm-policy-router/spec.md`（Requirement 2「fallback 链执行」，主规范未改）
**关联 issue**: #77（harden-llm-gateway-governance 终审遗留——「fallback 执行器未接线业务调用点，fallback_from 只记最后一跳」）
**变更类型**: 修 bug · 意图不变（规范已写明行为、代码未做到 → systematic-debugging + 复现测试，非 delta）

## 缺口（修复前，红测证据）

| 缺口 | 证据（修复前） |
|---|---|
| 执行器零生产调用方 | `gateway.complete_text_with_fallback` 仅测试调用；docstring 自认「业务调用点接线为 follow-up」 |
| 管线结构化节点不切链 | `nodes/_llm_utils.call_llm_for_json` 在 repair 耗尽（JSON 解析失败 / 字段校验失败）与四类 typed error（ContentFiltered/AuthError/ModelNotFound/UnsupportedCapability）下直接上抛，从不按 `fallback_chain` 切换 |
| `fallback_from` 只记最后一跳 | `gateway.py` 仅成功返回的 metadata 记 `ordered[idx-1]`；多跳链的中间跳在任何 trace 里都不可见（spec「每次切换 MUST 在 trace 记录」字面缺口） |
| 流式入口无法按 preset 选链成员 | `complete_stream` 无 `preset` 参数（非流式 `complete_text` 有）→ 链成员无法切换 |

复现（红）：`tests/nodes/test_llm_utils_fallback.py` 7 用例在修复前全红（缺链切换 + preset 未落）；
`tests/llm/test_gateway_fallback.py::test_every_switch_recorded_on_its_own_attempt_trace` 修复前
`KeyError: 'fallback_path'`；`tests/llm/test_gateway.py::TestCompleteStreamPresetPassthrough` 修复前
`TypeError: complete_stream() got an unexpected keyword argument 'preset'`。

## 实现要点

1. **链计划共享**（`gateway.fallback_attempt_plan`）：primary + registry `fallback` 名 → `select_profile`
   能力偏序校验 → 请求级 primary 打头去重 → 截到 `_MAX_FALLBACK_ATTEMPTS=3`。非流式执行器与
   节点路径共用同一计划，避免两套口径漂移。
2. **每次切换各自成观测记录**：切换后的尝试把 `fallback_from`（触发切换的上一成员）与
   `fallback_path`（含本次在内的完整尝试路径）写入该次 generation 的 trace metadata；
   成功返回的 metadata 同步携带两者（多跳可审计）。
3. **管线节点接线**（`call_llm_for_json`）：触发集 = 四类 typed error + 本路径的合同 repair 耗尽
   （`json.JSONDecodeError` / pydantic `ValidationError`）；触发类 typed error 不在本 profile
   空转重试，直接交给链；链耗尽上抛最后一个错误（重试 ≠ 降级）。
4. **链懒解析**：首次尝试沿用请求级配置透传（`preset=None`，与修复前同语义）；链只在首次失败后
   解析——happy path 与 `TESTING=1` stub 路径零解析成本，也不在触发错误前引入新的配置错误面
   （链解析失败时上抛原错误，不换错误面）。

## 验证矩阵

| 验证项 | 依据 | 结果 |
|---|---|---|
| 链切换（repair 耗尽 / validate 耗尽） | `tests/nodes/test_llm_utils_fallback.py`（9 用例，先红后绿） | ✅ 切换发生、成员按 preset 选中、请求级配置不带到成员 |
| 触发类 typed error 直接切链 | 同上 `TestTypedErrorSwitchesProfile` | ✅ ContentFiltered 不空转重试；链耗尽上抛 AuthError；上限 3 成员 |
| 非触发错误不切换 | 同上 `test_non_trigger_error_does_not_switch` | ✅ RuntimeError 沿既有同 profile 重试语义上抛 |
| 每次切换落 trace（多跳） | `tests/llm/test_gateway_fallback.py`（新增 2 用例） | ✅ 第 2/3 次尝试各带自己的 `fallback_from`/`fallback_path`；原始 metadata 不被破坏 |
| 流式入口 preset 透传 | `tests/llm/test_gateway.py::TestCompleteStreamPresetPassthrough` | ✅ `preset="ark-glm"` → 实际请求 model=`openai/glm-5.2` |
| 懒解析不变量 | `tests/nodes/test_llm_utils_fallback.py::TestLazyChainResolution`（2 用例） | ✅ happy path 零 `fallback_attempt_plan` 调用；链解析失败不盖原错误 |
| 既有语义不回退 | `tests/nodes/test_call_llm_for_json.py`（15 用例，2 条 raises 用例固定单 profile 链） | ✅ 同 profile 强化指令重试、瞬时故障重试、validate 重试语义不变 |
| 节点/LLM/图 5 层回归 | `pytest tests/nodes tests/llm tests/test_graph_5layer.py tests/test_models.py` | ✅ 722 passed |
| 全量后端 | `uv run pytest` | ✅ 3121 passed / 2 skipped（18:59，Docker/Langfuse 在线） |
| lint / 类型 | `ruff check` / `ruff format --check` / `mypy`（改动文件） | ✅ 0 issues |

## 人工抽查项（⬜ 待人工）

1. ⬜ Langfuse 实机确认：制造一次真实切换（如临时把 primary 的 key 置为无效）后，链成员那次
   generation 的 metadata 是否带 `fallback_from` / `fallback_path`（本轮为单测级验证，未跑真链路）。
2. ⬜ `metrics.md` §3 决策队列：env/请求级 primary 的 fallback 链声明方式（见下）。

## 已知边界 / follow-up

- **生产当前不触发切换（配置面缺口）**：`.env` 经 `LLM_MODEL` 解析出的 profile 名为 `env:openai/glm-5.3`，
  不携带 `fallback` 声明 → 链长 1 → 本轮接线在现网配置下不产生实际切换。链内容如何为 env/请求级
  primary 声明（沿用 registry preset 的 fallback / 新增 env 变量 / 保持现状）属配置语义决策，未擅自发明。
- **文本节点未接线**：`nodes/analysts.py`（4 处）与 `nodes/research_manager.py`（1 处）直调
  `call_llm_streaming`（无 repair 阶段），typed error 仍直接上抛；ReAct 路径
  （`harness` → `complete_stream_async`）同样未接线。二者与管线路径共用同一 `fallback_attempt_plan`，
  可低成本扩展。
- 触发集口径为「spec 四类 typed error + 合同 repair 耗尽」；`OutputTruncatedError` 等 retryable 错误
  仍走各自既有的同 profile 升级重试（规范未列入切换触发条件）。

## 结论

[x] 单测/回归/lint/类型全部通过，缺口有红→绿证据；可进入人工抽查（Langfuse 实机确认后收口 issue #77 该子项）
[ ] 存在失败项，需修复后重新验证
