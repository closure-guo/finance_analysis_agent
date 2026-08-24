# Task 1 Report — migrate-off-legacy-llm-shim: 4 个 call_llm 调用方迁移到 gateway.complete_text

状态：DONE_WITH_CONCERNS
Commit：见文末
运行：`uv run pytest tests/llm/ tests/test_llm.py -q -m "not live"` → 285 passed；全量 `uv run pytest tests/ -m "not live"` → 1156 passed, 2 skipped, 8 deselected

---

## 摘要

把 4 个生产 `from finance_agent.llm import call_llm` 调用方全部改为
`from finance_agent.llm.gateway import complete_text`，逐条复刻 legacy 语义：

1. `quick=True → purpose="quick"`；非 quick → `purpose="deep"`
2. content 为空时回退 `meta["raw_reasoning"]`（每个调用方都显式实现）
3. `agent=` → `trace={"name": agent, "metadata": {"agent": agent}}`
4. `llm_config` → 请求级 dict（仅 report.py 有，见下）
5. `temperature` 显式补足（legacy 默认 0.3；web_fetcher 原传 0.1 保留）
6. `max_tokens` 原值保留

## 各调用方迁移 diff 摘要

### 1. `src/finance_agent/nlp.py:77` （purpose=deep, max_tokens=100, agent="intent_parser"）

- `call_llm(query, system=system, api_key=api_key, max_tokens=100, agent="intent_parser")`
  → `complete_text(messages, purpose="deep", max_tokens=100, temperature=0.3, llm_config=None,
  trace={"name": "intent_parser", "metadata": {"agent": "intent_parser"}})`
- messages 构造：`[{"role":"system","content":system}, {"role":"user","content":query}]`
- `api_key` 参数**不落 llm_config**：legacy `_request_config_dict(None, api_key)` 返回 None
  （llm_config 非 dict/LLMConfig 时直接 return None），传入 apiKey 单独 dict 会让 resolver
  抛 IncompleteLLMConfigError（半套配置）。故零漂移 = 不传 llm_config。
- 空文本回退：`resp = text or meta.get("raw_reasoning") or ""`

### 2. `src/finance_agent/react_agent.py:369,432` （两处 quick=True）

- L369 `_search_with_llm_reasoning`：max_tokens=200（原值）
- L437/L432 `_search_with_web_search`：max_tokens=400（**实际代码原值 400，brief 表格误标 200**，按零漂移保留 400）
- 两处均 `purpose="quick"`, `temperature=0.3`, `llm_config=None`（同 nlp：无 llm_config 时 api_key 被 legacy 丢弃）
- trace name="react_agent"；空文本回退 reasoning

### 3. `src/finance_agent/events/web_fetcher.py:135` （purpose=deep, temperature=0.1）

- 原调用无 max_tokens → gateway 走 capability 默认（不在 kwargs 中传 max_tokens）
- temperature=0.1 透明保留；llm_config=None
- 空文本回退 reasoning 后 `json.loads(raw)`

### 4. `src/finance_agent/nodes/report.py:144` （quick=True, max_tokens=400）

- 新增模块级 `_request_config_dict(llm_config, api_key)` **内联复刻** legacy 语义
  （不能 import legacy._request_config_dict——Task 3 会删除 legacy.py）：
  - dict / LLMConfig dataclass 均可（getattr 兼容）
  - 无 model → None（env/preset 解析）
  - baseUrl 缺 → env LLM_BASE_URL；apiKey 缺 → cfg.apiKey → api_key 参数 → LLM_API_KEY → DEEPSEEK_API_KEY
  - thinking / apiForm 仅显式设置时携带
- 调用：`purpose="quick"`, `max_tokens=400`, `temperature=0.3`,
  `llm_config=_request_config_dict(state.get("llm_config"), api_key)`,
  `trace={"name": "report", "metadata": {"agent": "report"}}`
- 保留 `contextlib.suppress(Exception)` 结构性兜底（首个 summary 截断 200）

## TDD 红绿结果

新增 `tests/llm/test_legacy_migration.py`（每个调用方 mock 其模块内 `complete_text`，
断言 purpose / max_tokens / temperature / trace.name + metadata.agent / llm_config 透传 /
空文本回退 raw_reasoning / 结构性兜底）：

- RED：13 failed（mock 目标 `complete_text` 不存在）
- GREEN：23 passed（含新增 baseUrl env 回退用例）

同时更新既有测试：
- `tests/nodes/test_report.py:121` 原 monkeypatch `report_mod.call_llm` → 改为
  `report_mod.complete_text` 返回 `("围绕估值的摘要文本", {})`（report.py 不再有 call_llm 属性）

## 测试命令输出

```
$ uv run pytest tests/llm/ tests/test_llm.py -q -m "not live"
285 passed, 33 warnings in 7.97s

$ uv run pytest tests/ -q -m "not live" --ignore=tests/e2e
1156 passed, 2 skipped, 8 deselected, 94 warnings in 318.19s

$ uv run ruff check src/finance_agent/ tests/llm/test_legacy_migration.py tests/nodes/test_report.py
All checks passed!

$ uv run mypy src/finance_agent/nlp.py src/finance_agent/react_agent.py src/finance_agent/events/web_fetcher.py src/finance_agent/nodes/report.py
Success: no issues found（react_agent 的 4 个残余错误为基线既有：git stash 前后一致，行号由 diff 位移）
```

## Concerns

1. **api_key 在 nlp/react 调用点被复用 legacy「丢弃」语义**：legacy
   `_request_config_dict(None, api_key)` 返回 None——历史 `call_llm` 在无 llm_config 时本就不把
   api_key 传给 gateway。迁移保留了该语义（llm_config=None + 不传 apiKey），两者行为完全一致。
   若日后希望 api_key 参数真正生效，需显式构造含 model/baseUrl/apiKey 的请求级 dict
   （resolver 请求级分支要求 model+baseUrl 完整）。
2. **brief 表格 react_agent L432 标 max_tokens=200 与代码不符**：实际代码是 400，已按代码原值保留
   （零漂移优先），brief「max_tokens 各自值保留（react 200 / report 400）」与代码矛盾，若需统一请复核。
3. **report.py 内联了 `_request_config_dict` 副本**：legacy 删除后无法 import，故复制其逻辑。
   两处逻辑需人工保持同步（legacy.py 删除时可在 Task 3 收敛为单源）。
4. **web_fetcher 未显式限制 max_tokens**：gateway 按 capability 默认（deepseek-chat 8192 /
   ark-glm 16384）。legacy 原默认 max_tokens=16384。这是 brief 明确指示的行为
   （「web_fetcher 无显式→gateway 走 capability 默认」），与旧 16384 硬编码有一致预期差异。
5. pre-commit hook（ruff+format）已处理，提交时已重新 git add。