# Tasks: add-report-data-disclosures

- [x] 报告头部确定性渲染「行情数据截止」（kline 最后交易日；缺失/空/不可解析时省略），
      TDD 单测覆盖在场与缺失两态（tests/nodes/test_report.py）
- [x] sentiment_analyst.md 增补外部口径显式化约束（口径主体 + 新闻源口径标注 + 未明降权）
- [x] prompt 契约测试覆盖（tests/test_prompt_contracts.py）
- [x] `uv run python scripts/deploy_prompts.py` 发布新 prompt 版本
- [ ] 人工验证报告落 tests/validation/（真实管线抽查：头部截止日期声明 + 板块口径表述）
