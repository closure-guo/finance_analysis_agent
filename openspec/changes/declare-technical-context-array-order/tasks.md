# Tasks: declare-technical-context-array-order

- [x] 技术指标 context 明示「时间正序（旧→新），列表末尾为最新一期」（analysts.py，TDD `TestTechnicalContextArrayOrder`）
- [x] 技术分析师 prompt 反幻觉规则增加「引用 -1 前核对序列尾部」自证约束，并经 deploy_prompts.py 发布（14 OK / 0 fail，technical_analyst 1301 chars）
- [x] TDD：复现测试——`tests/nodes/test_analysts.py::TestTechnicalContextArrayOrder` 钉死方向声明；`tests/test_prompt_contracts.py::TestTechnicalArrayOrderContract` 钉死 prompt 契约
- [ ] 冒烟回归：修复后深跑 ≥1 只趋势异动股，技术类 claim FAIL 率较 54% 显著回落（live，待执行/人工）
- [x] 校验器 citation.py 零改动；`uv run pytest -m "not live"`（1531 passed）/ ruff / mypy（3 文件零错误）全绿