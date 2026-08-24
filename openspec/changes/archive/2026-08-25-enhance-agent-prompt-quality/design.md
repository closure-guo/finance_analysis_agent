# Design: enhance-agent-prompt-quality

## Context

`src/finance_agent/prompts/*.md` 是各角色 LLM 提示词模板，经 `load_prompt_with_meta` 加载（Langfuse production label 优先，本地 .md 兜底）。对比 TradingAgents / ai-hedge-fund 后确认差距：提示词只定义"输出什么结构"（JSON schema），缺乏"怎么分析 / 怎么辩论 / 置信度怎么标"的方法论与约束。LangGraph 图结构与输出 schema 不变的前提下，提示词文本是行为质量的主要杠杆。

## Goals / Non-Goals

**Goals**
- 为 4 个分析师补反幻觉硬规则 + 分析方法论指引
- 为 3 类辩论者补对抗性指令（引用-反驳结构）
- 为 trader / risk_judge / fund_manager 补决策语义（action 档位、position_size、confidence 锚、approve/reject/return 语义）
- 为 research_manager 补评级表态指令（明确倾向 + 均衡取舍理由）
- 为 deep_mode / report.py 摘要补"仅基于输入材料"约束
- 收敛股票解析 LLM 提示词到单一实现，清理死代码
- 提供契约测试防止提示词编辑漂移

**Non-Goals**
- 不改变输出 JSON schema、LangGraph 节点结构、state 字段
- 不改前端渲染与 SSE 管道
- 不在本轮实现 Langfuse 新版本发布流程自动化（只需在实施时手动发布 production label 并与本地一致）
- 不对 quick_mode / follow_up_mode / events/web_fetcher / harness 兜底 prompt 做改动（内容已成熟或职责简单）

## Decisions

### D1: 以本地 .md 为权威改动载体

改动直接落在 `prompts/*.md`，契约测试针对本地模板断言。Langfuse 启用时 implementation 阶段需把新模板发布为 production label，否则线上行为不生效（load 逻辑已有 warning）。

- 备选：只改 Langfuse 侧（console 编辑）。否决：不可版本化、不可测试、不可 review。

### D2: 指令集中为「段」（section）而非散句

每个提示词按固定小节组织：`## 分析方法论`、`## 反幻觉硬规则`、`## 决策语义`（按角色适用）。契约测试用"小节标题 + 关键句"断言，而非全文快照，避免措辞微调导致测试崩塌。

- 备选：逐句断言。否决：措辞迭代成本高。

### D3: 契约测试用 stub LLM 而非快照比较

测试加载模板后断言必需段存在（`assert "反幻觉硬规则" in template` 等价物），并复用现有 `TESTING=1` stub 跑一条最小管线冒烟，验证渲染不破坏 JSON schema。不引入黄金文件。

- 备选：golden file 快照。否决：提示词高频迭代期维护成本高。

### D4: 分析要点与阈值指导从公开常识取材

方法论（ROE/PE/RSI 等指标判读）取材自通用投研常识与 TradingAgents/ai-hedge-fund 已验证的 prompt 结构，不引入新数据源。

### D5: research_manager 保持自由文本、加评级表态指令

research_manager 维持"非 JSON 文字输出"（避免破坏下游 trader 摘要拼接），但在文本结构上强制三段式：明确评级倾向 → 核心依据 → 均衡时取舍理由。示教性约束即可达成，无需改 schema。

- 备选：改结构化 JSON（仿 TradingAgents ResearchPlan）。否决：需同步改 trader/report 的消费逻辑，超本期范围。

### D6: 股票解析收敛以 react_agent 为权威

生产路径 search_stock_tool（四级降级）已完整覆盖 nlp.resolve_stock 功能，故收敛方向为：删除 `src/finance_agent/nlp.py` 中的 LLM 冗余解析（resolve_stock/_resolve_with_llm）与 legacy 测试引用，删除 `react_agent.py` 中未被引用的 `REACT_SYSTEM_PROMPT`。契约测试断言单一实现存在、死代码不在。

- 备选：保留 nlp.py 作 fallback。否决：两套契约不一致（一套有 reason/need_search、一套没有）且均无生产调用，保留徒增漂移风险。

## Risks / Trade-offs

- [Langfuse production label 覆盖本地改动] → 实施时新建 label 版本并同步；契约测试检测到漂移时以测试为准
- [提示词变长导致 token 成本上升] → 体量控制在每文件 +20~60 行，只补方法论与约束不补冗余示例
- [过度约束约束 LLM 质量] → 硬规则限定"不得编造"，方法论为建议性（SHOULD 语气），不硬性规定输出格式以外的表达方式
- [nlp.py 删除波及 legacy 迁移测试] → 同步更新 tests/llm/test_legacy_migration.py 中对 _resolve_with_llm 的引用；仅删冗余解析，保留 app_search 等公共能力
- [research_manager 评级可能被下游截断] → 三段式文本衔接现状 text 输出，trader/report 消费逻辑零改动

## Migration Plan

1. 修改 `prompts/*.md`（11 个文件：4 分析师 + 3 辩论者 + trader + risk_judge + fund_manager + research_manager + deep_mode）
2. 修改 `src/finance_agent/nodes/report.py:178` 摘要 prompt（补"仅基于输入材料"约束）
3. 收敛股票解析：删除 `src/finance_agent/nlp.py` 冗余 LLM 解析 + `react_agent.py` 的 REACT_SYSTEM_PROMPT 死代码；更新 `tests/llm/test_legacy_migration.py`
4. 新增契约测试文件 `tests/` 下（对齐现有测试结构）
5. 跑 `uv run pytest` + `uv run ruff check` + `uv run mypy`
6. 如线上 Langfuse 启用：发布新 production label 版本
7. 人工抽查一份报告，确认输出质量提升且 schema 不变

## Open Questions

- 是否需要把 quick_mode / follow_up_mode（对话编排层）也纳入本轮？当前设计不纳入，保持最小范围。