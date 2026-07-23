# 009 - "热门股票"类时效性查询被错误路由进深度分析管线

## 日期

2026-07-17

## 状态

已修复

## 问题现象

用户输入：

```text
分析一下热门股票
```

系统没有先进行澄清或搜索，而是直接调用 `run_deep_analysis` 进入 5 层深度分析管线。

## 影响范围

- 所有包含时效性、非具体股票名称的短查询（如"热门股票"、"今天推荐什么"）都可能被错误路由。
- 深度分析管线基于单只股票运行，
- 对"热门股票"这类无明确标的的查询，会导致 LLM 在 `search_stock` 阶段幻觉出一只股票（如贵州茅台）并直接触发分析，
- 用户体验受损，且浪费了较长的管线运行时间。

## 根因分析

三处关键词列表都遗漏了"热门"，导致"热门"没有被识别为需要搜索/澄清的时效性词：

1. **入口层** `src/finance_agent/api.py` 中 `_time_sensitive_keywords` 只包含 `["推荐", "热点", "今天", "今日", "最近", "最新", "利好", "买入"]`，没有"热门"，所以入口预调 `web_search` 的闸门没有打开。

2. **工具层** `src/finance_agent/react_agent.py` 中 `_classify_input` 的 `_concept_keywords` 也没有"热门"。"分析一下热门股票"是 8 字纯中文短句，没有数字、没有概念词 → 被分类为 `name`（股票名称）。

3. **分类为 `name` 后**，走到 `search_stock_tool` 的 STEP 2c LLM 常识推理。LLM 对"热门股票"这类时间敏感的查询，容易凭借记忆幻觉出一只真实存在的热门股（如贵州茅台 600519），并以高置信度返回。AKShare 验证 600519 确实存在后，工具返回单候选、高置信度（`confidence: 0.9`）。

4. **ReAct Agent 看到单候选高置信度**，按 `deep_mode.md` 规则直接调用 `run_deep_analysis`，进入 5 层管线。

## 修复方案

1. 在 `src/finance_agent/react_agent.py` 新增模块级常量 `_TIME_SENSITIVE_KEYWORDS`，统一包含"热门"、"热点"、"推荐"、"今天"等时效性词。

2. 在 `search_stock_tool` 的 LLM 常识推理（STEP 2c）前加确定性守卫：命中时效性关键词时直接跳过 LLM 推理，避免幻觉出单只股票。此时落到 Web Search（STEP 3）或 AKShare 模糊搜索（STEP 4），返回多候选并标记 `needs_confirmation: True`，由 Agent 反问用户选择。

3. `_classify_input` 也使用同一常量，把命中时效性词的查询直接分类为 `description`，而不是 `name`。

4. `src/finance_agent/api.py` 入口层的 `_time_sensitive_keywords` 改为复用 `react_agent._TIME_SENSITIVE_KEYWORDS`，避免两份列表再次不一致。

5. 更新 `src/finance_agent/prompts/deep_mode.md`，在多个示例和规则中加入"热门"，让 Agent 在 prompt 层面也明确看到"热门"需要先 `web_search`。

## 修改文件

- `src/finance_agent/react_agent.py`
- `src/finance_agent/api.py`
- `src/finance_agent/prompts/deep_mode.md`
- `tests/test_search_stock_tool.py`（新增回归测试）

## 回归测试

新增 `tests/test_search_stock_tool.py` 中两个测试类：

- `TestClassifyInput`：验证"热门股票"、"推荐股"被分类为 `description`，而"贵州茅台"仍为 `name`。
- `TestSearchStockTimeSensitiveGuard`：验证"热门股票"跳过 LLM 常识推理；当 Tavily 可用时走 Web Search 并返回多候选；概念词（如"白酒龙头"）仍正常走 LLM 推理。

运行结果：

```bash
uv run pytest tests/test_search_stock_tool.py::TestClassifyInput tests/test_search_stock_tool.py::TestSearchStockTimeSensitiveGuard -q --tb=short
# 9 passed
```

## 经验教训

- 关键词硬编码分散在多个入口、工具、prompt 中，是这次 bug 的主要原因。未来应将"时效性/非具体查询"判断逻辑集中到单一模块，并通过测试覆盖同义词变体（如"热门"、"热点"、"热股"）。
- LLM 常识推理对时间敏感输入不可靠，必须在调用前用确定性规则拦截，而不是依赖 LLM 自觉遵守 prompt 里的"先搜索"指示。
- 这个案例说明：即使输入很短（"热门股票"），只要包含"非具体股票"语义，就应该返回多候选/澄清，而不是单候选进管线。
