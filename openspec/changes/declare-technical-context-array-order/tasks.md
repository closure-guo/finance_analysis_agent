# Tasks: declare-technical-context-array-order

- [x] 技术指标 context 明示「时间正序（旧→新），列表末尾为最新一期」（analysts.py，TDD `TestTechnicalContextArrayOrder`）
- [x] 技术分析师 prompt 反幻觉规则增加「引用 -1 前核对序列尾部」自证约束，并经 deploy_prompts.py 发布（14 OK / 0 fail，technical_analyst 1301 chars）
- [x] TDD：复现测试——`tests/nodes/test_analysts.py::TestTechnicalContextArrayOrder` 钉死方向声明；`tests/test_prompt_contracts.py::TestTechnicalArrayOrderContract` 钉死 prompt 契约
- [x] 冒烟回归（2026-08-31 中际旭创 deep run, trace ebbf234e）：FAIL 率 54.2% → **4.3%**（23 claims / 1 FAIL / 3 UNVERIFIABLE）。注：本次 run kline 拉取失败、无技术数据，方向机制的端到端观察待有技术数据 run 补验（单元层已由 TestTechnicalContextArrayOrder / TestTechnicalArrayOrderContract 钉死）
- [x] 校验器 citation.py 零改动；`uv run pytest -m "not live"`（1531 passed）/ ruff / mypy（3 文件零错误）全绿