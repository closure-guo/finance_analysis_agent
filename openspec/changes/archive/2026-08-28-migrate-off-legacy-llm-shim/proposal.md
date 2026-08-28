# Proposal: migrate-off-legacy-llm-shim

## Why

`finance_agent.llm.legacy`（`call_llm` / `call_llm_stream` / `call_llm_with_tools` / `LLMConfig`）自 5.1-C 起已是纯 gateway 薄壳：内部全部转调 `gateway.complete_text` / `complete_stream` / `complete_with_tools`，自身只保留「签名兼容 + 参数映射 + DeprecationWarning」。它现在只制造双重维护成本：

1. **双入口漂移**：`temperature` 默认值（legacy 0.3 vs gateway 无默认）、`quick=True` 参数只有 legacy 认、`_request_config_dict` 的 camelCase → dict 映射与 resolver 的解析语义并行存在；改一处漏另一处是持续缺陷源（如本次截断续写 delta 只改 gateway，legacy 路径依赖转调才被动获得）。
2. **调用的废弃噪音**：生产代码每次调用都打 DeprecationWarning，但调用方从未迁移——「已弃用」状态与实际依赖矛盾，掩盖真实架构。
3. **语义驻留 legacy**：「content 为空回退 reasoning」（`legacy.py:206-208`）与 `_ERROR_CLASS_BY_NAME` 错误还原（`legacy.py:279-281`）只存在于薄壳层，gateway 调用方无法获得，迁移必须显式复刻。

**目标**：删除 legacy 薄壳，生产代码全部直连 gateway，单一入口、无双重语义。

## What Changes

- **迁移 4 个 `call_llm` 生产调用方**到 `gateway.complete_text`：`nlp.py:77`（intent 解析）、`react_agent.py:369,432`（stock/query 解析，含 `quick=True`）、`events/web_fetcher.py:135`（事件提取）、`nodes/report.py:144`（focus 摘要）；**复刻「空 content 回退 reasoning」语义**（读 `metadata["raw_reasoning"]`）。
- **迁移 `nodes/_llm_utils.py:201` 的 `call_llm_stream` 到 `gateway.complete_stream`**：复刻 `(kind, text)` 迭代协议（thinking/answer）与 error 事件 → typed error 还原（`_ERROR_CLASS_BY_NAME`）。`_llm_utils.py` 是 deep 管线总入口（含本次截断续写 delta 的 32768 翻倍重试逻辑），**行为必须逐字节对齐**。
- **删除 `legacy.py`** 与 `__init__.py` 的 re-export（`__init__.py:9-14`）；`LLMConfig` 类型迁移到调用方显式 dict 或直接删除（调用方传 dict）。
- **测试迁移**：`tests/test_llm.py` 约 40 处 `from finance_agent.llm import call_llm/...` 改调 gateway 对应入口；既有行为断言（thinking 流、错误类型、空文本回退）保留。
- **参数映射复刻清单**（迁移时逐条验证，缺一即行为漂移）：`quick→purpose`、`temperature` 默认、`max_tokens` 默认 16384、`agent→trace.name`、`session_id/stock_code/prompt_name/prompt_version→trace.metadata`、`llm_config（LLMConfig|dict）→请求级 dict`。

## Capabilities

- **New Capabilities**: 无
- **Modified Capabilities**: `llm-provider-gateway`（MODIFIED：gateway complete 三入口成为唯一生产 LLM 入口；REMOVED：legacy 薄壳适用的 deprecated 双入口不再存在）

## Impact

- **核心代码**：`src/finance_agent/llm/legacy.py`（删除）、`src/finance_agent/llm/__init__.py`（去 re-export）、`nlp.py` / `react_agent.py` / `events/web_fetcher.py` / `nodes/report.py` / `nodes/_llm_utils.py`（改调 gateway）
- **风险最高**：`_llm_utils.call_llm_streaming` 迁移（deep 全管线 + 截断续写 fallback）；「空 content 回退 reasoning」与 `quick` 档位在 4 个调用方逐一复刻
- **测试**：`tests/test_llm.py` 大量改写；`tests/llm/` 回归保持
- **收益**：单入口、消除 DeprecationWarning、`temperature`/`quick` 语义收敛到 gateway 契约