# Tasks: align-ark-glm-param-defaults

参考：`specs/llm-provider-gateway/spec.md`（行为契约）。测试按 TDD「先红后绿」，重点 `tests/llm/test_provider_options.py` / `test_resolver.py` / `test_budget_governance.py`。

## 1. registry：ArkGLMOptions + 三表注册 + max_tokens 对齐

- [x] 1.1 `registry.py`：新增 `ArkGLMOptions`（pydantic BaseModel，`extra="forbid"`，`reasoning_effort: Literal["max","high","low"] | None = None`）；注册 `PROVIDER_OPTIONS_SCHEMAS["ark-glm"]`、`DEFAULT_PROVIDER_OPTIONS["ark-glm"]={"reasoning_effort":"max"}`、`REQUEST_OVERRIDABLE["ark-glm"]={"reasoning_effort"}`
- [x] 1.2 `registry.py:106-108`：ark-glm `max_output=16384 → 65536`、`default_params={"max_tokens": 16384} → {"max_tokens": 65536}`。TDD：失败测试（断言 derive_output_budget 对 ark-glm 返回 65536）→ 实现 → 通过

## 2. adapter：apply_provider_options 支持 ark-glm

- [x] 2.1 `litellm_adapter.py::apply_provider_options`：从「provider=="deepseek"」单分支扩展为「deepseek 或 ark-glm（provider=="openai" 且 profile.name 含 ark/模型名含 glm）可消费 provider_options」；ark 分支产出 `reasoning_effort` 请求参数（不产出 deepseek 的 thinking/suppress_temperature 专属逻辑）。TDD：失败测试（ark profile 带 provider_options 时调用 apply_provider_options 返回 {reasoning_effort:...}）→ 实现 → 通过

## 3. resolver：env/request 分支方舟推理配置

- [x] 3.1 `_provider_options_from_env`：模型含 "glm" 时用 `DEFAULT_PROVIDER_OPTIONS["ark-glm"]` + `LLM_REASONING_EFFORT` 覆盖（与 deepseek 分支同模式）。TDD：失败测试（LLM_REASONING_EFFORT=high + glm 模型 → provider_options.reasoning_effort=="high"）→ 实现 → 通过
- [x] 3.2 `_provider_options_from_request`：白名单扩展到 `ark-glm`（REQUEST_OVERRIDABLE 已注册，函数按 provider 取白名单——确认 provider="openai" 时能否取到 ark 白名单，必要时按模型名分支）。TDD：请求级 llm_config reasoning_effort=low → 最终请求参数 low

## 3.5 源头统一：deep 管线入口默认 65536

- [x] 3.5.1 `nodes/_llm_utils.py:358` `_call_base`：`max_tokens=16384 → 65536`（deep 管线总入口，覆盖 registry 默认的显式传参）；`escalate` 翻倍 `32768 → 131072`（官方最大，避免翻倍后仍小于 base）。TDD：更新三条断言（65536 基线、131072 翻倍）。`harness/litellm_client.py:140` 的 quick 路径 16384 **保留**（ReAct 短输出，注释明确为 legacy 合同保真）

## 4. 验证收尾

- [x] 4.1 `uv run pytest tests/llm/ tests/test_llm.py -q -m "not live"` 全绿；全量 `uv run pytest tests/ -m "not live"` 不回归（重点 test_budget_governance / test_provider_options / test_resolver / test_registry / test_gateway*）
- [x] 4.2 `uv run ruff check` / `uv run mypy` 通过（改动零告警）
- [x] 4.3 `openspec validate align-ark-glm-param-defaults` 通过；`openspec validate --strict` 无回归
- [x] 4.4 提交