# Design: add-agent-readable-conclusion

## Context

`AnalystReport` 现含 `summary`（面向 RM 的精简分析语言，黑话）与 `markdown`（章节渲染）。评估材料（judge 输入 `analyst_reports` 拼装、人工标注表 agent 摘要）复用 `summary`，普通人读不懂每份 agent 立场；截取式「一句话」预览被证与正文重复、无信息量（2026-09-09 回归）。需要一个**普通人可读的结论字段**，评估链路直接读它，不再从自由文本猜。

## Approach

1. **模型：必填强校验**。`AnalystReport` 增加 `plain_conclusion: str = Field(..., min_length=1)` + 非空白校验（复用 FundManagerDecision.reasoning 的强校验模式——reasoning 曾因可选导致「无理由决策」不可审计，本字段同样不允许静默缺失）。解析降级路径（`parse_degraded`）在分析师节点内回填可读占位（如「技术面数据缺失，无法给出结论」），保证字段非空、管线不中断。

2. **Prompt：4 个分析师输出该字段**。`technical/macro/fundamental/sentiment` 四个 prompt 的结构化输出契约加 `plain_conclusion`，并约束「面向普通人可读、一句话结论+解释」；变更后经 `scripts/deploy_prompts.py` 发布（prompt-deploy-consistency 门禁：不发布则 eval 拒跑）。

3. **评估链路优先读取**。`evals/extract.py::_summarize_analyst_reports` 改为 `plain_conclusion or summary or conclusion`；`evals/judge_calibration/material.py` 的 agent 摘要（`_expand_agent_sections`）文本源随之（analyst_reports 变量已含 plain_conclusion）。原截取式摘要已在前序 bugfix 移除。

4. **向后兼容**。旧 trace 报告对象无该字段 → `.get()` 回退 `summary`，零中断、零报错。

## Alternatives Considered

- **方案 A：把 `summary` 语义改成普通人可读**——破坏 RM 消费语义（RM 依赖精简黑话做多空裁决），不选。
- **方案 B：评估材料用 LLM 现生成摘要**——额外 token 成本 + 引入第三方观点污染校准，不选；用 agent 自带字段零成本。
- **方案 C：新字段但可选（默认空）**——重蹈 FM reasoning 曾可选导致「无理由决策」不可审计的教训；必填 + 降级占位才是防静默缺失的正确姿势。

## Risks

- **风险 1：LLM 偶发缺 `plain_conclusion` 致校验失败中断**。对策：解析降级路径已存在（`parse_degraded`），降级时回填可读占位，不中断管线、不静默产出。
- **风险 2：prompt 变更使 eval 门禁拒跑（`_verify_prompt_sync`）**。对策：发布与实现同批执行 `deploy_prompts.py`；eval 基线重跑归入本 delta 任务。
- **风险 3：旧 trace 回退遗漏**。对策：extract 用 `.get()` + 专项测试覆盖「无字段回退 summary」场景。

## 影响范围

`src/finance_agent/models.py`（字段）、`src/finance_agent/nodes/analysts.py`（解析/降级）、4 个分析师 prompt、`evals/extract.py`、`evals/judge_calibration/material.py`；测试 `tests/test_models.py` / analyst 节点测试 / `tests/evals/test_extract.py` / `test_judge_calibration_material.py`；部署 `scripts/deploy_prompts.py`。