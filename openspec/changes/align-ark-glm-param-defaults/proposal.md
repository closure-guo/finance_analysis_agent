# Proposal: align-ark-glm-param-defaults

## Why

当前 ark-glm（方舟 GLM-5.3）的 max_tokens 与 reasoning 参数与官方默认值不一致，且 reasoning_effort 无配置入口：

1. **max_tokens=16384 严重低于官方默认 65536**（官方最大 131072，建议 ≥1024）。GLM reasoning 与正文共享配额（`reasoning_forced=True`），16384 在长 JSON 节点（fundamental_analyst）里 reasoning 吃光配额 → `finish_reason=length` 正文为空（实验实锤：`answer=''` + length）→ 按既有契约抛 OutputTruncatedError 中断整条 item。官方默认 65536 给 reasoning + 正文留足空间，从源头消除这一截断模式。
2. **reasoning_effort 无配置入口**：`.env` 的 `LLM_REASONING_EFFORT` 只被 `_provider_options_from_env` 消费且仅 `deepseek/` 前缀（`resolver.py:120-130`）；方舟（provider="openai"）走 env 分支时 `provider_options={}`（`resolver.py:273`），`apply_provider_options` 对非 deepseek 直接 `return {}`（`litellm_adapter.py:427-428`）。GLM-5.3 官方默认 reasoning_effort=max，但当前完全无法配置/透传。

## What Changes

- **ark-glm max_tokens 对齐官方默认 65536**：`registry.py:106-108` `max_output=16384 → 65536`、`default_params={"max_tokens": 16384} → {"max_tokens": 65536}`。deep 长 JSON 节点从源头避免 reasoning 吃空配额。
- **ark-glm reasoning_effort 显式配置入口**：
  - `registry.py` 新增 `ArkGLMOptions`（reasoning_effort: `max/high/low`，GLM-5.3 仅这三档），注册 `PROVIDER_OPTIONS_SCHEMAS["ark-glm"]`、`DEFAULT_PROVIDER_OPTIONS["ark-glm"]={"reasoning_effort":"max"}`（官方默认）、`REQUEST_OVERRIDABLE["ark-glm"]={"reasoning_effort"}`；
  - `litellm_adapter.apply_provider_options`：支持 `ark-glm`（provider="openai" 但 profile.name 含 ark 语义）消费 provider_options → 产出 `reasoning_effort` 请求参数（litellm/vLLM 泛化，OpenAI 兼容端点透传）；
  - `resolver._provider_options_from_env`：识别方舟 GLM 模型（`glm` in model）时用 `DEFAULT_PROVIDER_OPTIONS["ark-glm"]` + `LLM_REASONING_EFFORT` 覆盖（与 deepseek 分支同模式）；`_provider_options_from_request` 白名单增加 `ark-glm`。

## Capabilities

- **New Capabilities**: 无
- **Modified Capabilities**: `llm-provider-gateway`（MODIFIED：provider_options 消费方扩展支持 openai/ark-glm 的 reasoning_effort 透传；registry 静态默认对齐官方）

## Impact

- **核心代码**：`registry.py`（ArkGLMOptions + 三表 + max_tokens）、`litellm_adapter.py::apply_provider_options`（分支扩展）、`resolver.py`（_provider_options_from_env / _provider_options_from_request 方舟分支）
- **间接**：截断续写 delta 的触发频率大降（65536 配额下深长 JSON 不再 reasoning 吃空）；`_llm_utils` 32768 翻倍重试变为罕见兜底
- **测试**：`tests/llm/test_provider_options.py`、`test_resolver.py`、`test_budget_governance.py` 增补（65536 默认断言、ark reasoning_effort 透传断言、env/request 覆盖断言）
- **风险**：65536 是「预算上限」而非「固定消耗」——模型输出完自然 stop 不浪费 token；成本影响仅当输出确实长。reasoning_effort=high/low 观察级配置，可通过 `.env`/请求级覆盖调整。