# LLM Gateway 5.1-C: 旧路径收口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development

**Goal:** harness 消费 CanonicalEvent（异步入口）、`call_llm`/`call_llm_with_tools` 薄壳化，legacy.py/harness 去 litellm 直连，grep 门禁收紧为仅 adapters。

**Architecture:** gateway 增加 `complete_stream_async`（raw_acompletion + tool_call 事件 + per-chunk 超时 + retryable 重试）与 `complete_with_tools`；`LiteLLMClient.chat_stream` 变为 CanonicalEvent→LLMResponse 翻译层（构造签名/loop/Stub 不动）；provider 逻辑全部收进 adapter/registry。

**Tech Stack:** Python 3.12 / pytest / asyncio。

## Global Constraints

- 设计档案：`docs/design/LLM Provider Gateway 完整架构设计.md` §8（adapter 唯一消费方、tool delta 合并归属 adapter）+ §7 CanonicalEvent（tool_call 事件）。
- 行为合同保真：harness「重试耗尽上抛」、loop 的 LLMResponse 字段（reasoning_delta/text_delta/tool_calls/is_finished）、`call_llm` content 为空回退 reasoning、Langfuse 观测 metadata 键位——全部保持。
- `loop.py`、`agent_factory.py`、`StubLLMClient`、`test_react_loop.py` 不改。
- 断言零弱化；既有测试全绿；commit 格式 `feat(llm)/test(llm): ...`。
- `drop_params=True` 本轮不移除（judge 直连依赖，登记 follow-up）。

---

### Task 1: adapter 工具增量合并收口（§8 职责 3）

**Files:**
- Modify: `src/finance_agent/llm/adapters/litellm_adapter.py`
- Test: `tests/llm/adapters/test_tool_call_merge.py`（新增）

**Produces:**
- `ToolCallAccumulator`：`add(delta)` 按 index 聚合 id/name/arguments（delta 形态 `{id, function: {name, arguments}, index}`，与 litellm 流式 delta 同构；移植自 harness/litellm_client.py:271-287）
- `finalize_tool_calls(acc) -> list[dict]`：输出 `[{id, function: {name, arguments: <str>}}]`；arguments 经 `_normalize_arguments_str` + 嵌套 `{"arguments": X}` 解包（自 `_normalize_tool_args` 移植：单 key "arguments" 且值为 str/dict 时解包）
- `sanitize_request_messages(messages, capability) -> list`：`sanitize_messages_for_profile` 的薄包装（gateway 各入口复用命名）
**TDD:** 红 → 实现 → `uv run pytest tests/llm -q` 绿 → commit `feat(llm): adapter 工具增量合并收口 — ToolCallAccumulator/finalize/sanitize 包装`。

---

### Task 2: gateway `complete_stream_async`

**Files:**
- Modify: `src/finance_agent/llm/gateway.py`
- Test: `tests/llm/test_gateway_stream_async.py`（新增）

**Produces:** `async def complete_stream_async(messages, *, purpose="deep", max_tokens=None, tools=None, tool_choice="auto", temperature=None, llm_config=None, trace=None, chunk_timeout=60.0, max_retries=3, retry_delay=1.0) -> AsyncIterator[CanonicalEvent]`
- 请求构造复用 resolve_profile/guard/derive_output_budget/apply_provider_options；`sanitize_request_messages`；`tool_choice` 传 raw_acompletion（guard_params_supported 已有 required 守卫）
- 事件：reasoning/text 增量；tool_call 事件（Accumulator 终态，finish_reason ∈ {tool_calls, stop(带 calls), 无 reason(带 calls)} 三分支，对齐 litellm_client.py:290-343）；finished；error
- per-chunk `asyncio.wait_for(aiter.__anext__(), chunk_timeout)` 超时按当前 attempt 处理（计入重试）
- `normalize_exception` 后 `retryable` 且未耗尽 → 退避 `retry_delay * 2**attempt` 重试（重试前 yield 无事件直接重来）；耗尽/不可重试 → **raise**（保 loop 合同）
- Langfuse 观测复用 complete_stream 模式；output 含 `{answer, reasoning, tool_calls?, usage}`；tool_calls 结构 `[{name, arguments}]`
- 测试 mock `finance_agent.llm.adapters.litellm_adapter.raw_acompletion`（async 返回 async iterator；chunk 含 tool_calls delta 形态）。

**TDD:** 红 → 实现 → 绿 → commit `feat(llm): gateway complete_stream_async — tool_call 事件/per-chunk 超时/重试耗尽上抛`。

---

### Task 3: complete_text 增强 + complete_with_tools + legacy 两入口薄壳

**Files:**
- Modify: `src/finance_agent/llm/gateway.py`（complete_text 加 `trace` + sanitize；新增 `complete_with_tools`）
- Modify: `src/finance_agent/llm/legacy.py`（call_llm/call_llm_with_tools 薄壳；`_build_kwargs`/`_is_deepseek`/`_resolve_key` 处置见下）
- Modify: `tests/test_llm.py`（call_llm/with_tools/_build_kwargs 测试迁移）
- Modify: `src/finance_agent/llm/__init__.py`（若导出面变化）

**Produces:**
- `complete_text(..., trace=None)`：观测对齐 call_llm 契约（name/metadata→output {answer, reasoning}+usage）；sanitize_request_messages
- `complete_with_tools(messages, *, tools, tool_choice="auto", purpose="quick", max_tokens=None, temperature=None, llm_config=None, trace=None) -> resp`：guard + sanitize + apply_provider_options + raw_completion；观测 output 含 tool_calls；返回原始 resp
- `call_llm` 薄壳：DeprecationWarning；purpose=quick/deep；temperature 透传（默认 0.3）；llm_config 经 `_request_config_dict` 复用；**content 为空回退 reasoning 在 shell 层保留**（complete_text 返回 (text, meta)，text 已空时 shell 从…注意：complete_text 只返回 text——需让 complete_text 返回的 text 保留原语义或 shell 直接用 trace? 处置：complete_text 不做回退，shell 在 text=="" 时用 resp? 不可得。改为：complete_text 增加 include_reasoning_fallback? 简化：complete_text 返回 (text, metadata) 且 metadata 带 raw_content/raw_reasoning（不进 trace），shell 据此回退）
- `call_llm_with_tools` 薄壳 → complete_with_tools；deepseek thinking+tools 保持开启（provider_options 语义，reasoning_must_echo_on_tool=True 回传）——计划内语义修正（零生产调用方）
- legacy.py 移除 `import litellm`/`_build_kwargs`/`_is_deepseek`；`_build_kwargs` 的 25 个测试重写为 gateway 侧断言（model/temperature/thinking 经 provider_options）
**TDD:** 红（薄壳测试 + 迁移后测试）→ 实现 → `uv run pytest tests/llm tests/test_llm.py -q` 绿 → commit `feat(llm): call_llm/call_llm_with_tools 薄壳转调 gateway (5.1-C)`。

---

### Task 4: LiteLLMClient.chat_stream 薄壳化（LLMResponse 翻译层）

**Files:**
- Modify: `src/finance_agent/harness/litellm_client.py`（chat_stream 重实现为 complete_stream_async 包装；删 _build_kwargs/deepseek 分支/tool 合并/自有重试/自有 Langfuse；`_normalize_tool_args` 删除——已迁 adapter；构造签名与 prompt 元数据保留 → trace 透传）
- Modify: `tests/test_litellm_client.py`（mock complete_stream_async 或 raw_acompletion；保留 retry/tool_calls/Langfuse 断言语义，观测断言转向 gateway 层或经 trace 验证）
- Modify: `tests/test_tool_args_normalize.py`（import 目标改 adapter）
- 不动：loop.py / agent_factory.py / StubLLMClient / test_react_loop.py

**TDD:** 红 → 实现 → `uv run pytest tests/test_litellm_client.py tests/test_react_loop.py tests/test_agent_factory_testing_branch.py tests/test_tool_args_normalize.py tests/llm -q` 绿 → commit `feat(llm): LiteLLMClient.chat_stream 收口 gateway — CanonicalEvent→LLMResponse 翻译层`。

---

### Task 5: 门禁收紧 + 全量验证 + 文档

- `tests/llm/test_grep_gate.py` allowlist 收为仅 `llm/adapters/litellm_adapter.py`；`grep -rn "import litellm" src/finance_agent` 验证仅 adapter
- drop_params 注释补 follow-up 指向（judge 路径迁移后白名单化）
- `uv run pytest -k "not live" -q` 全绿；ruff；mypy 与基线一致
- 真实验证：quick 模式真实对话（走 harness 链路，确认 thinking/tool/report 流式）——controller 执行
- tasks.md 5.1 勾选 + 验证报告 C 轮小节
- commit `chore(llm): 5.1-C 门禁收紧 + 验证材料`
