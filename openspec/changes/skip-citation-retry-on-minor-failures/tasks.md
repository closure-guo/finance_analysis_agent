# Tasks: skip-citation-retry-on-minor-failures

- [ ] TDD：复现测试——汉森制药冒烟场景（46 claim / 1 FAIL / 2.2%）经 after_citation 后不派发重试轮（直接 render + 降级标记）
- [ ] after_citation 增加轻微失败放行分支（FAIL ≤ 1 且失败率 ≤ 5%），既有停滞降级与轮数上限不回归
- [ ] 降级标记落 trace（可判读字段），与既有 `citation_retry_deescalated` 通道一致
- [ ] 冒烟回归：修复后深跑 ≥1 只标的，确认轻微失败不再触发分析师全量重跑（iteration_count 保持 1）
- [ ] `uv run pytest` / ruff / mypy 全绿