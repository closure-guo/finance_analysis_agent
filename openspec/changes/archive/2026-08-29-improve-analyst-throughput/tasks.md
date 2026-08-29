# Tasks: improve-analyst-throughput

- [x] 技术指标 context 裁剪：technical_analyst 序列裁剪为最近 60 期 + 窗口说明（单测覆盖 250 期裁剪 / 45 期保留 / 缺失兜底）
- [x] citation 重试降级：失败率无显著改善（≥ 上一轮 80%）时提前放行渲染，上限 3 轮不变（单测覆盖降级放行 / 改善续跑 / 上限不变）
- [x] 降级决策落 Langfuse trace 可判读标记（verify_citations span metadata `citation_retry_deescalated` + 失败率序列，单测覆盖）
- [x] 全量验证：uv run pytest / ruff check / mypy 通过（live 标记用例预存在失败不计入）
