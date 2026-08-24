# Proposal: enhance-agent-prompt-quality

## Why

与 GitHub 主流 trading agent 项目（TradingAgents、ai-hedge-fund）对比后，本项目各角色提示词（`src/finance_agent/prompts/*.md`）偏薄：辩论者缺少对抗性指令、分析师缺少分析方法论与反幻觉硬规则、决策层缺少评级语义与置信度锚点。导致多 Agent 管线名义上"辩论"实则各说各话，LLM 输出置信度数字缺乏语义，存在幻觉与数据虚构风险。

## What Changes

- 为 4 个分析师提示词（fundamental/macro/technical/sentiment）补充**分析方法论 + 反幻觉硬规则**：明确"只用输入数据推理、以数据最新日期为现在、不得编造数字、数据不足必须明说"。
- 为 bull/bear/risk 辩论者提示词补充**对抗性辩论指令**：要求逐条引用并反驳对手上一轮论点，而非复述报告。
- 为 trader 提示词补充**决策语义契约**：position_size 各档定义、confidence 分档语义、推荐依据报告权重的指引。
- 为 risk_judge/fund_manager 提示词补充**评级量表语义**（buy/sell/hold/watch 各档含义与取舍规则）。
- 为全部分析师统一**数据缺失兜底**：缺省时必须显式标注并降级 confidence，不得假装有数据。
- 为 research_manager 提示词补充**结构化评级表态**：要求给出明确的看多/看空/中性倾向 + 依据摘要 + 证据均衡时的取舍说明（当前仅 3 行自由文本，Trader 拿到的输入质量不可控）。
- 为 deep_mode 提示词补充**输出约束**：摘要必须仅基于 run_deep_analysis 工具输出，不得补充工具未提供的数字。
- **硬编码 prompt 治理收敛**：report.py 摘要 prompt 补"仅基于输入材料"约束；股票名称解析 LLM 调用收敛至 react_agent.py 单一实现、移除 nlp.py 冗余解析；清理 react_agent.py 未引用的 REACT_SYSTEM_PROMPT 死代码。

不改变输出 JSON schema，不改变 LangGraph 节点结构（行为契约不变），只改提示词模板文本 + 收敛硬编码 prompt。

## Capabilities

- **New Capabilities**: `agent-prompt-contracts`（角色提示词的行为契约：反幻觉规则、辩论对抗、决策语义、数据缺失兜底）
- **Modified Capabilities**: 无（主规范库无既有 prompt 行为定义）

## Impact

- 代码：仅修改 `src/finance_agent/prompts/*.md` 模板文本（Langfuse production label 启用时需同步发布新版本 label，否则本地改动被 Langfuse 版本覆盖）
- 测试：新增基于 call_llm 的提示词契约单测（用 stub LLM 断言提示词含必需指令段）与 e2e stub 套件回归（如适用）
- 行为：分析报告/辩论内容/决策质量变化；结构化输出 schema 不变，前端渲染不受影响
- 依赖：无新增