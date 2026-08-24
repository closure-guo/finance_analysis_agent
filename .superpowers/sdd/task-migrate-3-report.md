# Task 3 report — migrate-off-legacy-llm-shim: 删 legacy + LLMConfig 找平 + 测试迁移

## 状态
DONE（一个 concern 见文末：合并使用的 test_llm_stream_thinshell.py 删除）

## 改动摘要

### 1. LLMConfig 落点：方案 A（独立模块）
- 新建 `src/finance_agent/llm/config.py`：LLMConfig dataclass（camelCase 字段原样保留，
  `model / baseUrl / apiKey / thinking / apiForm`，含 N815 noqa）。
- `src/finance_agent/llm/__init__.py`：`LLMConfig` 改从 `config` re-export（保持
  `from finance_agent.llm import LLMConfig` 兼容）；`call_llm / call_llm_stream /
  call_llm_with_tools` re-export 删除；`get_profile_preset / list_presets /
  resolve_profile / CanonicalEvent / CanonicalRequest / Capability / ModelProfile`
  re-export 保留。
- `api.py` / `agent_factory.py` 的 import 行**无需改动**（继续走 `finance_agent.llm` 包
  级 re-export），`_to_llm_config` 契约不变。
- 节点层 `_request_config_dict`（`_llm_utils.py` / `nodes/report.py`）用 getattr 兼容，
  无需改。

### 2. legacy.py 删除
- 删除 `src/finance_agent/llm/legacy.py`（369 行，原薄壳 + LLMConfig）。
- `grep -rn "from finance_agent.llm import call_llm\|call_llm_stream\|call_llm_with_tools" src/` 零命中；
  `grep -rnE "\bcall_llm\b|\bcall_llm_stream\b|\bcall_llm_with_tools\b" src/` 仅命中注释。

### 3. __init__.py 最终面貌（见文末块）

### 4. tests/test_llm.py 迁移（33 个用例，语义逐条保留）
- `call_llm` → `gateway.complete_text`；`call_llm_with_tools` → `gateway.complete_with_tools`。
- mock 目标不变：`adapter.raw_completion` / `langfuse_tracing.get_langfuse` / `open_span`。
- 保留断言语义：
  - thinking/answer 分流（complete_text output.answer/reasoning 落 observation）
  - 空文本 → meta.raw_reasoning（调用方回退契约，`test_complete_text_exposes_reasoning_when_content_empty`）
  - tool_calls 落 output（含空列表省略 key、降级 open_span 路径、no-op 降级不报错）
  - prompt_name/version metadata、agent/session/stock 过滤字段、observation 命名 litellm: 退化
  - api_key/baseUrl 请求级优先、env 回退、auto-prefix openai/ 语义
- 删除原 DeprecationWarning 用例（薄壳已删，无 DeprecationWarning 可测）。
- 模块级说明改为测 gateway；新增 3 个 legacy 移除守卫用例 + 1 个 LLMConfig re-export 保留用例。

### 5. 其他连带清理（简报约束外，删除 legacy 的必然结果）
- `tests/llm/test_llm_stream_thinshell.py`（99 行）删除：其唯一测试对象是
  `legacy.call_llm_stream`（双路径对拍），薄壳删除后必然 ImportError；回归命令含
  `tests/llm/`，必须处理。gateway 流式行为已由 `tests/llm/test_gateway_stream.py`
  覆盖。
- `tests/test_trace_content_live.py`：`call_llm_with_tools` → `complete_with_tools`
  （@live，nightly 防漂移用例保持有效）。
- `tests/nodes/test_call_llm_streaming_gateway.py::TestLegacyNotUsed`：原锚点
  `patch("finance_agent.llm.call_llm_stream", ...)` 因符号已删无法 patch；改为
  `test_legacy_call_llm_stream_symbol_gone` 断言包级符号不存在 + 保留直连 gateway 断言。

## TDD 红绿
- RED：新增 `test_legacy_call_llm_removed_from_package` 等 3 个用例 → 删除 re-export 前
  `DID NOT RAISE ImportError`（红）。
- GREEN：`__init__.py` 清理 + `legacy.py` 删除后同命令 4 passed（含
  `test_llm_config_still_reexported_from_package`）。

## 验证输出
- 定向回归：`uv run pytest tests/llm/ tests/test_llm.py tests/test_api*.py -q -m "not live"`
  → **310 passed**。
- 全量：`uv run pytest tests/ -q -m "not live"` → **1165 passed, 2 skipped, 8 deselected**。
- `uv run ruff check src/ tests/` → All checks passed（--fix 处理 3 处末行换行）。
- `uv run mypy src/finance_agent/llm/` → Success（llm 包零告警）。
- mypy 全库在 api.py/agent_factory.py 有 17 个既有错误（git stash 验证改动前后一致，
  非本任务引入）。
- `openspec validate migrate-off-legacy-llm-shim` → valid。

## Commit
- `feat(llm): 删除 legacy 薄壳 + LLMConfig 迁 config.py + test_llm.py 迁移 gateway`
  （完整 hash 见 `git log --oneline`；amended 多次，以最终 HEAD 为准）

## Concerns
1. `tests/llm/test_llm_stream_thinshell.py` 删除不在简报 files 清单内，但它是「删
   legacy 后 tests/llm/ 回归必须全绿」的必然连带；其专项语义（薄壳对拍）随薄壳消失
   而失真，gateway 侧覆盖无空洞。如需保留「旧薄壳回归证明」可回填，但无实际价值。
2. api.py / agent_factory.py 既有 mypy 错误非本任务引入（dev 环境已知债务）。