# Tasks: skip-citation-retry-on-minor-failures

- [x] TDD：复现测试——`tests/test_routing.py::TestAfterCitationMinorFail`（minor_fail→render / 非轻微→retry / 上限优先）+ `tests/nodes/test_citation_node.py::TestCitationMinorFail`（40 条 1 FAIL=2.5% 设标志并落标记 / 13 条全 FAIL 不设）
- [x] after_citation 增加轻微失败放行分支（FAIL ≤ 1 且失败率 ≤ 5%），既有停滞降级与轮数上限不回归（21 routing 用例 + 16 citation_node 用例全绿）
- [x] 降级标记落 trace：`citation_minor_fail_deescalated` + fail_rates，走 update_current_span WARNING 通道（与既有 `citation_retry_deescalated` 一致）
- [ ] 冒烟回归：修复后深跑 ≥1 只标的，确认轻微失败不再触发分析师全量重跑（iteration_count 保持 1）（live，待执行/人工）
- [x] `uv run pytest -m "not live"`（1531 passed）/ ruff / mypy 全绿