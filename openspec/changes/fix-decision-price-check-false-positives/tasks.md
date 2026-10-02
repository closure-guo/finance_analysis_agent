# Tasks: fix-decision-price-check-false-positives

- [x] 缺陷 A：`_NON_PRICE_KEYWORDS` 追加 `var`/`在险价值`——VaR95 / VaR(95% / 在险价值95 语境的数值不再误报（688072 reasoning 原文回归用例）
- [x] 缺陷 B：`_BREAKDOWN_WORDS` 追加 `回撤至`/`回调至` + 同条目同数值 down+up 共现豁免 empty_trigger（688072 gen1/gen2 触发条件原文回归用例；spec 既有 22.61 空洞场景行为不变）
- [x] spec 场景 1 例子更正一致性：单元测试对齐 MODIFIED 后的场景（真幻觉「目标价 95 元」仍报、VaR95 不报）
- [x] incident 034 文档 + incidents README 索引（证据链、对评审原始「95 元幻觉」诊断的更正）
- [x] 全量验证：`uv run ruff check`、`uv run mypy`（零新增）、`uv run pytest`（全量）；验证证据落 tests/validation/
