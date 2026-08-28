# Delta for LLM Provider Gateway

## ADDED Requirements

### Requirement: gateway 为唯一生产 LLM 入口（legacy 薄壳移除）

系统 SHALL 将 `finance_agent.llm.legacy`（call_llm / call_llm_stream / call_llm_with_tools / LLMConfig）从生产链路移除：所有 LLM 调用 SHALL 直接经 `gateway.complete_text` / `gateway.complete_stream` / `gateway.complete_stream_async`，不再存在第二个 deprecated 入口。移除前 SHALL 完成既有调用方迁移并逐条复刻 legacy 语义。

#### Scenario: 生产调用方迁到 gateway

- **GIVEN** 原 legacy call_llm 调用方（nlp.py / react_agent.py / web_fetcher.py / report.py）
- **WHEN** 迁移到 `gateway.complete_text`
- **THEN** SHALL 复刻以下 legacy 语义：`quick=True → purpose="quick"`、`temperature` 默认 0.3、`max_tokens` 默认 16384、`content 为空时回退 reasoning_content`
- **AND** `agent` / `session_id` / `stock_code` / `prompt_name` / `prompt_version` SHALL 经 `trace` dict（name/metadata）透传，Langfuse 命名与过滤字段不丢失

#### Scenario: deep 管线流式入口迁移

- **GIVEN** `_llm_utils.call_llm_streaming` 原经 legacy call_llm_stream 消费流式
- **WHEN** 迁移到 `gateway.complete_stream`
- **THEN** SHALL 保留 `(kind, text)` 迭代协议（thinking→"thinking"，answer→"answer"）与 error 事件 → typed error 还原（原 `_ERROR_CLASS_BY_NAME` 映射）
- **AND** 截断续写 delta 的 32768 翻倍重试逻辑 SHALL 行为不变（续写优先、翻倍兜底）

#### Scenario: legacy 移除与 re-export 清理

- **WHEN** 全部调用方迁移完成且回归通过
- **THEN** 删除 `legacy.py` 及 `finance_agent.llm.__init__` 中对它的 re-export
- **AND** 代码库 SHALL NOT 再出现 `from finance_agent.llm import call_llm` / `call_llm_stream` / `call_llm_with_tools`（全库 grep 零命中）

## MODIFIED Requirements

### Requirement: litellm 适配收口

系统 SHALL 将所有 litellm 直接调用收口在 adapter 内（raw_completion / raw_stream / raw_acompletion），业务与 gateway 不直接 touch litellm。gateway complete 三入口（complete_text / complete_stream / complete_stream_async）SHALL 是生产代码唯一 LLM 入口。
(Previously: 系统 SHALL 将所有 litellm 直接调用收口在 adapter 内，业务与 legacy 薄壳经 gateway 转调，不直接 touch litellm。)

#### Scenario: 全库无 legacy 引用

- **WHEN** 执行 `grep -rn "from finance_agent.llm import call_llm\|legacy" src/`
- **THEN** SHALL 仅命中 `__init__.py` 注释性提及或零命中
- **AND** 生产代码 SHALL 全部经 `gateway.complete_*` 调用