# Proposal: add-agent-readable-conclusion

## Why

分析师输出的 `summary` 是给下游 RM 的精简分析语言（技术黑话，如「MACD 死叉」「多空对峙」），普通审计者在一致性评估、人工标注、报告评审中读不懂每个 agent 的真实立场；评估材料当前靠截取/启发式拼贴，产生无信息量重复与「半句话」导出的问题（2026-09-09 实测）。每个分析师应输出一句普通人可直接看懂的「结论+解释」独立字段，审计与评估材料直接读该字段，不再从自由文本里猜。

## What Changes

- `AnalystReport` 新增**必填字段** `plain_conclusion: str`：普通人可读的一句话结论+简短解释（如「技术面偏空：MACD 死叉、反弹动能存疑，不宜右侧追入」）；LLM 输出解析失败走降级路径时以可读占位回填，保证字段非空
- 4 个分析师 prompt（technical / macro / fundamental / sentiment）在结构化输出中包含该字段；prompt 变更走 `scripts/deploy_prompts.py` 发布（prompt-deploy-consistency 门禁）
- 评估材料与 judge 输入（`evals/extract.py` 的 analyst_reports 拼装、人工标注材料 agent 摘要）**优先展示 plain_conclusion**；旧 trace 无该字段时回退现状（summary 拼贴），不破坏既有评估

## Capabilities

### New Capabilities

（无——本次为既有契约与评估材料的扩展）

### Modified Capabilities

- `agent-node-contracts`: 新增 Requirement「分析师报告可读结论字段」——AnalystReport 必须含普通人可读的 `plain_conclusion`（必填非空 + 解析降级回填可读占位 + 测试覆盖）
- `agent-evaluation-suite`: 修改「事实性 claim 抽取/评估输入」链路——评估材料分析师节优先展示 `plain_conclusion`（普通人可读），而非黑话 summary 拼贴

## Impact

- `src/finance_agent/models.py`：`AnalystReport` 增加 `plain_conclusion`
- `src/finance_agent/nodes/analysts.py`：分析师输出解析，`plain_conclusion` 缺失/降级处理
- `src/finance_agent/prompts/technical_analyst.md` / `macro_analyst.md` / `fundamental_analyst.md` / `sentiment_analyst.md`：输出契约加该字段
- `evals/extract.py`：`_summarize_analyst_reports` 优先取 `plain_conclusion`
- `evals/judge_calibration/material.py`：agent 摘要展示读该字段
- 测试：`tests/test_models.py`、analyst 节点测试、`tests/evals/test_extract.py`、`test_judge_calibration_material.py`
- 部署：prompt 变更后必须 `scripts/deploy_prompts.py` 发布（AGENTS.md 红线），eval 基线随之需重跑