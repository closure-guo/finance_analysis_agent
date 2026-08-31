# Tasks: declare-technical-context-array-order

- [ ] 技术指标 context 明示「时间正序（旧→新），列表末尾为最新一期」
- [ ] 技术分析师 prompt 反幻觉规则增加「引用 -N 前核对序列尾部」自证约束，并经 deploy_prompts.py 发布
- [ ] TDD：复现测试——incident 022 中际旭创类样本（stated=窗口首元素 vs gt=尾部）经定向 context 后校验结果与真实最新值一致
- [ ] 冒烟回归：修复后深跑 ≥1 只趋势异动股，技术类 claim FAIL 率较 54% 显著回落
- [ ] 校验器 citation.py 零改动；`uv run pytest` / ruff / mypy 全绿