# Proposal: add-deep-summary-brief

## Why

`run_deep_analysis` 工具完成后，返回给 ReAct 摘要 LLM 的 `llm_output` 只截取报告**前 2000 字符**（`report_md[:2000]`）。报告正文多为 1 万+ 字符，前 2000 字符几乎全是图表列表与分析师章节开头；「多空辩论结论」「交易决策」「风控辩论」「基金经理决策」章节全部位于截断线之后。摘要 LLM 看不到这些章节，只能按 `deep_mode.md` 摘要指令「报告某章节缺失时写『本次分析未覆盖』」填充——实测拓荆科技分析（trace 04b872ae）的【一句话结论】与【多空分歧】均为「本次分析未覆盖」。

## What Changes

- `run_deep_analysis` 工具返回的 `llm_output` 从「报告前 2000 字符截断」改为**结构化结论摘要 + 报告正文节选**：从管线 `accumulated` 提取各层结论——多空辩论结论（`research_manager_conclusion`）、交易决策（`trader_plan`/`final_trade_decision`）、风控裁决、基金经理决策（`fund_manager_decision` + reasoning）、各分析师一句话——拼装成固定格式摘要块，再附报告正文前段供引用。
- 摘要块各字段做长度保护（如单字段截断），防工具结果体积失控（harness `tool_result_budget=50000` 仍为上限）。
- 不改变 `report_ready` 事件 metadata 与前端展示链路；`final_report_summary`（trace 根 span output）逻辑不动。

## Capabilities

### New Capabilities

- `deep-analysis-tool-feedback`: 定义 `run_deep_analysis` 工具返回给 Agent LLM 的内容契约——SHALL 包含各层结论章节，使摘要 LLM 具备填全全部摘要字段所需的材料（对齐 `agent-prompt-contracts`「摘要仅基于输入材料」）。

## Impact

- **代码**: `src/finance_agent/agent_factory.py` — `_make_run_deep_analysis` 内 `llm_output` 构造处（约 806-812 行）替换为结构化摘要构建。
- **测试**: `tests/test_deep_analysis_tool.py` — 增「工具输出包含辩论/交易/风控/基金经理结论」用例（fake graph 注入各层更新）。
- **行为**: 摘要 LLM 可基于工具输出填充全部摘要字段；前端摘要不再出现「本次分析未覆盖」placeholder（数据/章节缺失场景除外）。