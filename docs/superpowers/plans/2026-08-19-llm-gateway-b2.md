# LLM Gateway 5.1-B2: call_llm_stream 薄壳转调 gateway（按 §7.1 Provider Options）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development

**Goal:** `legacy.call_llm_stream` 薄壳化转调 `gateway.complete_stream`，provider 特有参数（thinking/reasoning_effort/extra_body）按设计档案 §7.1 落 `provider_options`（registry 三件套 + resolver 三层合并 + adapter 唯一消费）。

**Architecture:** provider 差异只存在于 registry（schema/defaults/白名单）与 adapter（消费映射）；resolver 组装 `ModelProfile.provider_options`（registry defaults < env 覆盖 < 请求级白名单覆盖）；gateway `complete_stream/complete_text` 增加 `temperature` 并应用 adapter 的 provider kwargs；薄壳只做签名适配（messages/purpose/llm_config env-补齐/事件转 tuple/error 重抛）。

**Tech Stack:** Python 3.12 / pytest / pydantic（registry schema）。

## Global Constraints

- 设计档案：`docs/design/LLM Provider Gateway 完整架构设计.md` §7.1 Provider Options + §8 Adapter 职责 7。
- 业务代码（含薄壳）零 provider 分支；`_is_deepseek` 类模型名判断不得进入新代码。
- `call_llm` / `call_llm_with_tools` / `_build_kwargs` 不动（仍被其余两入口使用）。
- 不收紧 grep 门禁（三入口 + harness 全部转调后再收）。
- `tests/llm/test_grep_gate.py` 必须保持通过（legacy.py 仍在 allowlist）。
- 既有测试保持全绿；受影响测试按 mock 目标迁移（`finance_agent.llm.legacy.litellm.completion` → `finance_agent.llm.adapters.litellm_adapter.raw_stream`）。
- commit 格式：`feat(llm): ...`；一个任务一个 commit。

---

### Task 1: provider_options 机制（types + registry + resolver）

**Files:**
- Modify: `src/finance_agent/llm/types.py`（ModelProfile 增加 `provider_options: dict[str, Any] = field(default_factory=dict)`）
- Modify: `src/finance_agent/llm/registry.py`（DeepSeekOptions schema + DEFAULT_PROVIDER_OPTIONS + REQUEST_OVERRIDABLE + deepseek-official preset 填 defaults）
- Modify: `src/finance_agent/llm/resolver.py`（三层合并）
- Test: `tests/llm/test_provider_options.py`（已存在红测试，含全部用例）

**Interfaces:**
- Produces:
  - `DEFAULT_PROVIDER_OPTIONS: dict[str, dict]`，deepseek → `{"thinking": "enabled", "reasoning_effort": "max"}`
  - `PROVIDER_OPTIONS_SCHEMAS: dict[str, type[BaseModel]]`，deepseek → DeepSeekOptions（thinking: Literal["enabled","disabled"]|None；reasoning_effort: Literal["low","high","max"]|None；拒绝未知 key）
  - `REQUEST_OVERRIDABLE: dict[str, set[str]]`，deepseek → `{"thinking", "reasoning_effort"}`；未登记 provider → 空/缺席
  - resolver：request 分支按 model 前缀取 defaults，叠加 llm_config 中白名单内字段（顶层 `thinking` 键 + 可选 `provider_options` dict），白名单外 key 抛 ValueError 家族；env 分支 deepseek 模型 → defaults + `LLM_THINKING`/`LLM_REASONING_EFFORT` 覆盖；named preset → preset.provider_options；非 deepseek → `{}`
- 既有 resolver 行为（原子性校验/前缀规则/judge 独立）不变。

**TDD 步骤：** 运行 `uv run pytest tests/llm/test_provider_options.py -q` 确认红 → 实现 → 绿 → `uv run pytest tests/llm -q` + `uv run pytest tests/test_resolver.py 2>/dev/null; uv run pytest tests/llm/test_resolver.py tests/llm/test_registry.py tests/llm/test_types.py -q` 全绿 → commit `feat(llm): provider_options 机制 — registry 三件套 + resolver 三层合并 (§7.1)`。

---

### Task 2: adapter 消费 + gateway temperature

**Files:**
- Modify: `src/finance_agent/llm/adapters/litellm_adapter.py`
  - 新增 `apply_provider_options(profile) -> dict`：registry schema 校验 `profile.provider_options`；provider=="deepseek" 且 `capability.extra_body_allowed` → `{"extra_body": {"thinking": {"type": <thinking>}}, "reasoning_effort": <effort>}`（None 字段省略）；thinking=="enabled" 时返回 `{"suppress_temperature": True}` 标志键（gateway 据此不发 temperature，对齐 legacy deep 分支）；其他 provider → `{}`
  - `raw_stream` / `raw_completion`：kwargs 无 `timeout` 时注入 `float(os.environ.get("LLM_TIMEOUT_SECONDS", "300"))`
- Modify: `src/finance_agent/llm/gateway.py`：`complete_stream` / `complete_text` 增加 `temperature: float | None = None`；组装 raw_* kwargs 时 `kwargs.update(apply_provider_options(profile))`，`suppress_temperature` 为 True 时不发 temperature、否则透传；观测/事件流逻辑不动
- Test: `tests/llm/adapters/test_apply_provider_options.py`（新增）+ `tests/llm/test_gateway_stream.py` / `test_gateway.py` 增补用例

**TDD 步骤：** 先写失败测试（deepseek enabled→extra_body+effort+suppress；disabled→无 suppress；非 deepseek→{}；schema 非法值抛错；raw_* timeout 注入与显式 timeout 不覆盖；complete_stream 收到 temperature/provider kwargs）→ 实现 → `uv run pytest tests/llm -q` 全绿 → commit `feat(llm): adapter 消费 provider_options + gateway temperature 透传`。

注意：complete_stream/complete_text 现有 kwargs 组装里 `**profile.default_params` 保留；`apply_provider_options` 结果 merge 在其后（可覆盖）。

---

### Task 3: legacy.call_llm_stream 薄壳化 + 测试迁移

**Files:**
- Modify: `src/finance_agent/llm/legacy.py`：`call_llm_stream` 重写为薄壳
  - `warnings.warn("call_llm_stream 已弃用：请使用 finance_agent.llm.gateway.complete_stream", DeprecationWarning, stacklevel=2)`
  - messages 构造保留（messages 参数覆盖 system+prompt）
  - `purpose = "quick" if quick else "deep"`
  - 新私有 helper `_request_config_dict(llm_config, api_key)`：LLMConfig → `{model, baseUrl, apiKey, thinking}`；baseUrl 缺 → env `LLM_BASE_URL`；apiKey 缺 → cfg.apiKey or api_key 参数 or `LLM_API_KEY` or `DEEPSEEK_API_KEY`；无 model → 返回 None
  - trace dict `{"name": agent or f"litellm:{model}", "metadata": _generation_metadata(prompt_name, prompt_version, agent, session_id, stock_code)}`
  - 迭代 `complete_stream(messages, purpose=purpose, max_tokens=max_tokens, temperature=temperature, llm_config=cfg_dict, trace=trace)`：reasoning→`("thinking", ev.reasoning)`；text→`("answer", ev.text)`；error 事件→重抛（`ev.finish_reason` 类名映射 `finance_agent.llm.errors` 类，默认 UnknownLLMError，消息取 `ev.raw.get("error", "")`）
  - 薄壳不再直接调 litellm（module 顶部 `import litellm` 保留——call_llm/call_llm_with_tools 仍用）
- Test: `tests/llm/test_llm_stream_thinshell.py`（新增：双路径对拍 / error→重抛 LLMError 子类 retryable / DeprecationWarning / 半套配置 IncompleteLLMConfigError）
- 迁移（mock 目标 → `finance_agent.llm.adapters.litellm_adapter.raw_stream`）：
  - `tests/test_llm.py`: `test_call_llm_stream_writes_reasoning_to_output` / `test_call_llm_stream_attaches_prompt_metadata` / `test_call_llm_stream_named_by_agent`（断言不变：tuple 流 / Langfuse metadata / observation name）
  - `tests/test_pipeline_llm_config.py::test_pipeline_llm_config_uses_correct_model`（改用完整 `LLMConfig(model="openai/gpt-4o-mini", baseUrl=..., apiKey=...)`，断言 raw_stream 收到 model）

**TDD 步骤：** 先写 thinshell 失败测试 → 实现薄壳 → 跑 `uv run pytest tests/llm tests/test_llm.py tests/test_pipeline_llm_config.py tests/test_pipeline_stub.py tests/test_llm_utils_metadata.py tests/nodes/test_call_llm_for_json.py -q` 全绿（迁移旧测试）→ commit `feat(llm): call_llm_stream 薄壳转调 gateway.complete_stream (5.1-B2)`。

**双路径对拍定义：** 同一 `raw_stream` mock（含 reasoning+text+finish=stop chunks）下，`call_llm_stream(prompt, system=..., llm_config=<完整dict>)` 的 tuple 流拼接（thinking 串 / answer 串）== `complete_stream(同 messages, llm_config=同)` 的 CanonicalEvent 流拼接（reasoning 串 / text 串）。

---

### Task 4: 全量验证 + 人工验证材料

**Files:**
- Modify: `tests/validation/llm-provider-gateway-validation.md`（B2 小节：单测/对拍/真实 quick 结果）
- Modify: `openspec/changes/add-llm-provider-gateway/tasks.md`（5.1 进度标注更新：B2 完成，C 未做）

**步骤：**
- `uv run pytest -k "not live" -q` 全绿（≥992 量级，数量随新增用例增长）
- `uv run ruff check` + `uv run mypy`（错误集与基线一致，零新增）
- `uv run pytest tests/llm/test_grep_gate.py -q`（门禁仍通过）
- 真实 quick 验证：`uv run python -c "..."` 调 `call_llm_stream(prompt, quick=True)` 连真实 LLM；无凭据则如实记录 ⬜
- commit `chore(llm): 5.1-B2 验证材料 + 进度登记`
