# Task 2 Report — migrate-off-legacy-llm-shim: _llm_utils.call_llm_streaming 迁移到 gateway.complete_stream

状态：DONE
Commit：`0f40496`（feat(llm): _llm_utils.call_llm_streaming 迁移到 gateway.complete_stream（保留续写 fallback））

---

## 摘要

把 deep 管线总入口 `src/finance_agent/nodes/_llm_utils.py::call_llm_streaming`
从 legacy `call_llm_stream` 薄壳迁移为直连 `gateway.complete_stream`，逐条复刻
迭代协议与错误还原：

1. **事件 → (kind, text) 映射**：`reasoning → thinking`（经 stream writer）、
   `text → answer`（拼接返回）、`finished → 忽略`、`error → 按
   `ev.finish_reason`（typed 类名字符串）经 `getattr(errors_mod, finish_reason,
   UnknownLLMError)` 还原为 typed error 后 raise（查不到 → UnknownLLMError，
   对齐 legacy._ERROR_CLASS_BY_NAME 缺省）。
2. **32768 翻倍重试 fallback 保留**：`escalate` 循环原样保留（仅换内部迭代消费
   目标），截断（`OutputTruncatedError`）→ 第二次调用 `max_tokens=32768`；
   retryable 非截断重试一次但预算不翻倍；非 retryable 立即上抛。
3. **请求构造复刻 legacy 薄壳**：
   - `system+prompt → messages [{"role":"system"},{"role":"user"}]`
   - `llm_config/api_key → 请求级 dict`（`_request_config_dict` 内联复刻，
     同 Task 1 report.py 模式；无需 import legacy）
   - `node_name → trace.name`（空时 `litellm:{model}`，model 经
     `_llm_model_for_name` 解析，env 回退 LLM_MODEL）
   - `prompt_name/prompt_version/node_name/stock_code → trace.metadata`
     （`_generation_metadata` 内联复刻，仅显式提供时写入）
   - 基线参数对齐 legacy 默认：`purpose="deep" / temperature=0.3 /
     max_tokens=16384`
4. **TESTING=1 stub 分支不变**（不触 LLM，`_NODE_NAME_MAP` 图节点名思考 token
   + `_stub_pipeline_answer`）。

## 迁移 diff 摘要

- `src/finance_agent/nodes/_llm_utils.py`
  - 新增模块级 `_DEFAULT_MODEL` / `_llm_model_for_name` / `_generation_metadata` /
    `_request_config_dict`（内联复刻 legacy 语义，供 Task 3 删 legacy 时无需逆向依赖）。
  - `call_llm_streaming` 主循环：`from finance_agent.llm import call_llm_stream`
    → `from finance_agent.llm.gateway import complete_stream`；`(kind, text)`
    元组迭代 → `CanonicalEvent` 迭代；error 还原用
    `getattr(_llm_errors, ev.finish_reason or "", _llm_errors.UnknownLLMError)`
    （errors 模块内类名即 finish_reason，与 legacy._ERROR_CLASS_BY_NAME 等价）。
  - 关键实现点：`escalate` 覆盖 `max_tokens` 时不能裸拼
    `complete_stream(messages, **_call_base, **escalate)`——本环境 Python
    （3.14）对两个 ** 展开的同键参数抛 `TypeError: got multiple values`；
    须先经 dict display 合并：`complete_stream(messages, **{**_call_base, **escalate})`。
- 测试迁移（mock 目标 `finance_agent.llm.call_llm_stream` → `finance_agent.llm.gateway.complete_stream`，
  `(kind,text)` 元组 → `CanonicalEvent`）：
  - `tests/test_llm.py`：3 个 legacy 流式用例改为经 `call_llm_streaming` 断言
    （reasoning 落 generation output / prompt metadata / agent 命名）。
  - `tests/test_llm_utils_metadata.py`：3 个透传用例改为断言 trace metadata。
  - `tests/test_pipeline_llm_config.py`：透传断言改走 complete_stream kwargs；
    llm_config 断言只校验 model（`_request_config_dict` 会按 env 回退链补
    apiKey，不做全 dict 断言）；端到端 `test_pipeline_llm_config_uses_correct_model`
    保持 adapter 层 mock 不变。
  - `tests/nodes/test_call_llm_for_json.py`：4 个流式重试用例改 mock
    complete_stream + CanonicalEvent；截断预算断言改为 `[16384, 32768]`
    （此前 `[None, 32768]`——新路径显式传 legacy 默认 16384）。
  - `tests/test_pipeline_stub.py`：stub 不触 LLM 断言与生产路径用例改 mock 目标。
  - 新增 `tests/nodes/test_call_llm_streaming_gateway.py`（9 个用例）：
    answer 拼接/finished 忽略、thinking 走 writer（含无 writer 丢弃）、error
    还原 typed error、截断翻倍重试 `[16384, 32768]`、retryable 非截断重试不翻倍、
    未知类名回退 UnknownLLMError、请求构造断言、以及「不再调用 legacy
    call_llm_stream」的迁移锚点。

## TDD 红绿

- RED：
  - `test_call_llm_streaming_uses_gateway_directly`（迁移锚点）：迁移前
    `call_llm_streaming` 仍调 legacy → AssertionError "legacy call_llm_stream 不应被调用"。
  - `tests/test_pipeline_llm_config.py` 3 个 llm_config 断言：迁移前 complete_stream
    收到的是原始 LLMConfig 对象而非请求级 dict → 断言失败。
  - 首轮新测试假体 4 个 error 用例因 fake 签名（不接受 positional messages 参数）
    + `_call_base`/`escalate` 裸 ** 同键 TypeError 失败，均为测试/实现自身问题，
    修复后转绿。
- GREEN：目标测试集 78 passed；必回归门禁 `tests/llm/ tests/test_llm.py` → 286 passed。

## 测试输出

```
$ uv run pytest tests/llm/ tests/test_llm.py -q -m "not live"
286 passed, 30 warnings in 7.85s

$ uv run pytest tests/llm/ tests/test_llm.py tests/test_pipeline*.py -q -m "not live"
330 passed, 1 failed（详见 Concerns：基线同样失败的先存 flake）

$ uv run pytest tests/nodes/test_call_llm_streaming_gateway.py \
    tests/test_llm_utils_metadata.py tests/test_pipeline_llm_config.py \
    tests/nodes/test_call_llm_for_json.py tests/test_pipeline_stub.py tests/test_llm.py -q -m "not live"
78 passed, 28 warnings in 24.64s

$ uv run pytest tests/ -m "not live" -q
1166 passed, 2 skipped, 8 deselected, 90 warnings in 340.46s

$ uv run ruff check <全部改动文件> && uv run ruff format --check <全部改动文件>
All checks passed!

$ uv run mypy src/finance_agent/nodes/_llm_utils.py
Success: no issues found in 1 source file

$ uv run mypy src/
Found 69 errors in 16 files（与基线完全一致：git stash 前后同为 69/16，
_llm_utils.py 不在错误列表，零新增）
```

## Concerns

1. **`tests/llm/ tests/test_llm.py tests/test_pipeline*.py` 组合下的先存 flake**：
   `tests/test_pipeline_stub.py::TestStreamingToolThinkPassthrough::
   test_streaming_tool_think_events_reach_agent_run_consumer` 在组合运行（含
   tests/llm/ 与 anchor/start_ts/timeout/write_blocking 等管线文件）时失败，
   RuntimeWarning `coroutine 'Queue.put' was never awaited`。git stash 后基线
   HEAD 同样失败（330 passed + 同 1 failed），与本迁移无关；单独运行或全量
   `pytest tests/ -m "not live"` 均通过（1166 passed）。建议后续单独立项修
   harness 异步队列跨文件污染。
2. **`max_tokens` 首轮显式 16384**：新路径显式传 legacy `call_llm_stream` 默认
   16384（对齐行为），因此截断重试断言由 `[None, 32768]` 变 `[16384, 32768]`
   ——语义等价，gateway 收到的预算序列与迁移前完全一致。
3. **内联 `_request_config_dict` / `_generation_metadata` / `_llm_model_for_name`**
   副本：legacy.py 删除后无法 import，故复制其逻辑（同 Task 1 report.py 模式）。
   Task 3 删 legacy.py 时可收敛为单源。
4. **Python 3.14 下 `f(**d1, **d2)` 同键抛 TypeError**：这是迁移后唯一的行为
   相关实现调整，已用 dict display 合并规避；不改变对外语义。
5. pre-commit hook（ruff --fix + ruff-format）与提交前人工 ruff 检查均已通过，
   提交时无二次改动。

## 提交

- `0f40496` feat(llm): _llm_utils.call_llm_streaming 迁移到 gateway.complete_stream（保留续写 fallback）
- 7 files changed, 492 insertions(+), 143 deletions(-)