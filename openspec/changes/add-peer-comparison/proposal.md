# Proposal: add-peer-comparison

## Why

用户点名多标的对比（如「对比贵州茅台和五粮液」）时，入口 Agent 只能回「一次只能分析一只股票」——`prompts/deep_mode.md` 对「点名多标的对比」没有显式意图分支，实测回复是即兴发挥且越出模板纪律（候选摘要末尾暗示「可分别查看后再自行比较」，违反模板「不要在末尾暗示批量分析或对比功能」）。

同时管线内其实已存在一条休眠的同业对比数据链：`AnalysisState.peer_codes` → `fetch_peer_data`（name/PE/PB）→ `relative_valuation` → `state.peer_comparison` 注入点（analysts.py）。三处断点使其对用户不可达：①入口 `run_deep_analysis` 工具签名不含 peer_codes，LLM 无法指定对标股（仅 HTTP 请求级闭包注入，前端从不传参）；②compute 层同业对比仅是标志位，缺格式化器注入 LLM context（Issue #4 挂账）；③deep_mode.md 核心约束明文禁止横向对比。问财对标（2026-10-08）已显示同业对比是诊股刚需。

## What Changes

- `prompts/deep_mode.md` 新增「点名多标的对比」意图分支：确定唯一主标的走完整管线（语义核心为主；歧义取点名第一只并告知可换主视角），其余 1–3 只作为对标股同跑注入；核心约束 3 从「不做横向对比」改为「对比以主标的+对标股形态在单条管线内完成」；核心约束 2（禁止并行多条完整管线）不变
- `run_deep_analysis` 工具签名暴露 `peer_codes` 参数（LLM 经 search_stock 解析名称后传入；HTTP 请求级闭包注入路径保留兼容，显式传参优先）
- `fetch_peer_data` 字段面扩展：估值组（name/PE/PB + 总市值）+ 财务组（营收同比/归母净利同比/毛利率/报告期，复用主标的同源的 `fetch_latest_period_snapshot`），字段组级降级（财务组失败不影响估值组产出）
- 新增同业指标格式化器（compute 层）：`peer_financials` → 结构化对照材料注入基本面分析师 context，替换现 `peer_comparison` 标志位占位（关闭 Issue #4）
- 报告基本面章节在 peer 数据存在时呈现同业对比段（指标对照 + 相对估值结论 + 数据口径/缺失声明），由基本面分析师 prompt 约束消费

**非目标**（明确不做）：串行多条完整管线 + 前端并排对比视图（L1，待 L0 验证价值后另行立项）；对比合成报告/跨报告辩论（L2）；管线原生多标的图结构（L3）；一致预期/股息率数据面扩容（问财 deferred 批其余项，另行立项）；前端任何交互变更。

## Capabilities

- **New Capabilities**: `peer-comparison`（对比请求识别与主标的解析、对标股参数传递、同业材料格式化注入、报告同业对比段呈现）
- **Modified Capabilities**: `analyst-data-sources`（「同业财务数据获取」字段面扩展 + 字段组级降级语义）

## Impact

- 代码：`src/finance_agent/prompts/deep_mode.md`、`agent_factory.py`（工具签名 + 闭包覆盖逻辑）、`data/akshare_client.py`（fetch_peer_data 字段扩展）、`nodes/fetch.py`、 `nodes/compute.py`（格式化器）、`nodes/analysts.py`（注入点换真材料）、基本面分析师 prompt（同业材料消费指令）
- Prompt：deep_mode.md 与基本面分析师模板修改后 MUST 执行 `uv run python scripts/deploy_prompts.py` 发布（prompt-deploy-consistency 门禁），指纹取证后定向覆盖
- 测试：formatter 单测、fetch 扩展字段与降级路径测试、工具签名/prompt 契约测试（`tests/test_agent_factory.py`、`tests/test_prompt_contracts.py` 扩展）、TESTING=1 stub 链路适配
- 交互类判定：无前端 UI/SSE/会话切换/状态流转变更 → 非交互类，免 §3 Step 4.5 E2E 门禁；LLM 报告质量走人工验证（`tests/validation/`）
- 关联：关闭 Issue #4；与问财 deferred 数据面批同源（一致预期/股息率不在本 delta 范围）
