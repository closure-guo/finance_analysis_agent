# Tasks: add-output-lint

- [x] R1 批注剥离：RED 测试（深南实例剥离、否定形态保留、辩论用语保留、非收尾形态保留、多命中计数、markdown/summary/plain_conclusion 覆盖）→ GREEN（analysts.py 三路径统一剥离）
- [x] R2 数值格式化：RED 测试（8.1/0.94/-20.22 → 原因串含 -13.06 且无浮点尾巴）→ GREEN（compute.py `_derive_pe_ttm` 格式化）
- [x] 回归：analysts/parse、compute、citation、report 相关子集全绿；ruff + mypy 零新增
- [x] 人工验证报告落 tests/validation/（含 8 份存量报告回扫：剥离器仅命中深南 1 处、格式化仅命中南航 1 处）
- [x] openspec validate add-output-lint --strict 通过
