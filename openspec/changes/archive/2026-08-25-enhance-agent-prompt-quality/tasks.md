# Tasks: enhance-agent-prompt-quality

## 1. 分析师提示词：反幻觉硬规则 + 方法论

- [x] 1.1 给 fundamental_analyst.md 追加「分析方法论 + 反幻觉硬规则」段（仅用输入数据、以数据最新日期为现在、不得编造数字、数据不足明示）
- [x] 1.2 给 macro_analyst.md 追加「分析方法论 + 反幻觉硬规则」段（同上 + 宏观指标判读指引）
- [x] 1.3 给 technical_analyst.md 追加「分析方法论 + 反幻觉硬规则」段（同上 + 指标判读阈值指引）
- [x] 1.4 给 sentiment_analyst.md 追加「分析方法论 + 反幻觉硬规则」段（同上 + 数据缺失时 confidence 降级语义）

## 2. 辩论者提示词：对抗性指令

- [x] 2.1 给 bull_debater.md 追加对抗性指令（逐条反驳对手论点、先引用再反论）
- [x] 2.2 给 bear_debater.md 追加对抗性指令（同上）
- [x] 2.3 给 risk_debater.md 追加对抗性指令（回应其它风险方位论点，引用-反驳结构）

## 3. 决策层提示词：语义契约

- [x] 3.1 给 trader.md 补 action 各档位语义 + position_size 档位定义 + confidence 分档锚点
- [x] 3.2 给 risk_judge.md 补评级量表语义（证据均衡/不足时的取舍指导）
- [x] 3.3 给 fund_manager.md 补 approve/reject/return 决策语义说明

## 4. 研究经理与编排层提示词

- [x] 4.1 给 research_manager.md 补评级表态指令（明确倾向→核心依据→均衡取舍理由三段式）
- [x] 4.2 给 deep_mode.md 补输出约束（摘要仅基于 run_deep_analysis 工具输出，不补材料外数值）
- [x] 4.3 给 report.py:178 摘要 prompt 补"仅基于输入材料、不引入材料外数值"约束

## 5. 硬编码 prompt 收敛

- [x] 5.1 删除 src/finance_agent/nlp.py 冗余 LLM 解析（resolve_stock/_resolve_with_llm），并更新 tests/llm/test_legacy_migration.py 引用
- [x] 5.2 删除 react_agent.py 中未引用的 REACT_SYSTEM_PROMPT 死代码
- [x] 5.3 契约测试断言：股票解析 LLM 提示词仅存在于 react_agent.py 一处、REACT_SYSTEM_PROMPT 已移除

## 6. 契约测试

- [x] 6.1 新增提示词契约测试（断言分析师含硬规则段、辩论者含对抗指令、决策层含语义段、research_manager 含评级指令），`uv run pytest` 通过（tests/test_prompt_contracts.py 32 用例全绿）
- [x] 6.2 `uv run ruff check` + `uv run mypy` 通过（ruff clean；mypy 69 错误为基线既有，与本 delta 无关）
- [x] 6.3 人工抽查一份报告，确认输出 schema 不变、质量提升（验证记录落 tests/validation/）

## 7. Langfuse 同步（如启用）

- [ ] 7.1 若 Langfuse production label 启用，发布新版本 prompt 并确认与本地一致（标注：当前本地兜底生效，若启用需另行发布）