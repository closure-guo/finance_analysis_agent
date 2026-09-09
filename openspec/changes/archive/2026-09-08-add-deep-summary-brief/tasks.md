# Tasks: add-deep-summary-brief

## 1. 失败测试（先行，先红）

- [x] 1.1 `tests/test_deep_analysis_tool.py` 新增：fake graph 注入各层结论（research_manager_conclusion / trader_plan / final_trade_decision / fund_manager_decision / analyst_reports），断言工具输出含辩论结论文本、交易决策方向、基金经理决策、分析师一句话
- [x] 1.2 报告 >2000 字符时，结论章节可见（非仅截断前 2000）
- [x] 1.3 某层结论缺失（如 fund_manager_decision 空）时不抛异常、不输出占位符
- [x] 1.4 既有用例回归（tool_result.output 含报告标题等）

## 2. 实现

- [x] 2.1 `_make_run_deep_analysis` 内 `llm_output` 构造替换为结构化结论摘要 + 报告正文节选（各字段长度保护）

## 3. 验证与收尾

- [x] 3.1 `uv run pytest tests/test_deep_analysis_tool.py` 全绿（12 passed）
- [x] 3.2 `uv run ruff check` + mypy（mypy 13 基线错误无新增）
- [x] 3.3 实跑验证：ReAct 深分析（session f66a2eb9），摘要【一句话结论】【多空分歧】等五字段全部填满，无「本次分析未覆盖」
- [x] 3.4 `openspec validate --strict add-deep-summary-brief`
- [x] 3.5 archive 前 tasks 全勾 + 门禁通过