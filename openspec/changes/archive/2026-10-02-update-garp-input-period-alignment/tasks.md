# Tasks: update-garp-input-period-alignment

- [x] `_try_garp` 负债率期次对齐：快照优先 → 年报回落，details 标注 `负债率_期次`/`ROE_期次`（TDD：快照有值过线 / 快照缺失回落且标注 / ROE 全年口径三用例）
- [x] 全量验证：`uv run ruff check`、`uv run mypy`（零新增）、`uv run pytest`（全量）；验证证据落 tests/validation/
