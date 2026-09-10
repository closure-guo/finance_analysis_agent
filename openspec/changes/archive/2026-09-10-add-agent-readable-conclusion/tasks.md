# Tasks: add-agent-readable-conclusion

## 1. 模型字段

- [x] 1.1 `AnalystReport` 增加 `plain_conclusion` 必填字段（`Field(min_length=1)` + 非空白校验）；TDD：缺失/空串/纯空白被拒绝，正常值通过（`tests/test_models.py`）

## 2. 分析师节点解析与降级

- [x] 2.1 `analysts.py`：LLM 输出缺 `plain_conclusion` / 解析失败时走降级路径回填可读占位（如「技术面数据缺失，无法给出结论」），`parse_degraded` 照常置位，管线不中断；测试覆盖降级回填

## 3. Prompt 输出契约与发布

- [x] 3.1 4 个分析师 prompt（technical/macro/fundamental/sentiment）结构化输出增加 `plain_conclusion`，并约束「面向普通人可读、一句话结论+解释」
- [x] 3.2 `scripts/deploy_prompts.py` 发布（14/14 成功，`_verify_prompt_sync` 一致；prompt 契约测试 54 绿）

## 4. 评估链路优先读取

- [x] 4.1 `evals/extract.py::_summarize_analyst_reports` 改为 `plain_conclusion` 优先（缺 → `summary` 回退）；测试覆盖含字段与缺字段两径
- [x] 4.2 `evals/judge_calibration/material.py` agent 摘要文本源随之（无字段旧 trace 回退不报错）；测试覆盖

## 5. 回归与验收

- [x] 5.1 全量非 live 测试通过（**2103 passed, 2 skipped, 12 deselected**）
- [x] 5.2 lint 与类型检查通过（`ruff check` 全 clean；`mypy` models/analysts/extract 无问题）
- [x] 5.3 干跑导出标注表：旧 trace 回退 `summary` 展示正常、导出不报错；新数据「plain_conclusion 优先」由单测（extract 优先 + 节点降级回填 + pipeline stub 全链路）覆盖