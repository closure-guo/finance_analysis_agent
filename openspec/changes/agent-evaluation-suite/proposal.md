## Why

Agent 输出质量的量化评估目前只有 `citation_pass` 一条腿（`nodes/citation_node.py:54-60`，全项目唯一显式上报的 Score），且只覆盖客观数据重算。主观质量（辩论是否实质交锋、决策论据是否有前文支撑、跨层结论是否一致、报告是否切题）完全无评估手段；prompt / 模型变更靠"跑单只票肉眼检查"，无回归保护；上线后质量漂移无监控。ADR-0010 第 126 行明确把 LLM-as-Judge 推迟为"未来 Eval Pipeline"，至今未立项；《Langfuse 评估体系设计文档》（`docs/design/Langfuse评估体系设计文档.md`）已完成设计但未转为可执行契约。本 delta 将该设计固化为 `evaluation` capability，形成"改 prompt → 跑回归 → 数据说话"的闭环。

## What Changes

1. **新建 `evaluation` capability** —— 定义确定性评估器、LLM-as-Judge 评估器、Dataset、实验回归、校准门禁、线上托管 Evaluator 六类行为契约。
2. **确定性评估器**（零 token）—— `section_coverage`（必备章节覆盖）、`ticker_match`（标的解析正确性），与已有 `citation_pass` 并列。
3. **LLM-as-Judge 评估器**（rubric 打分）—— `report_relevance` / `debate_quality` / `decision_grounding` / `consistency` 四个 Judge Score，裁判模型 `deepseek-chat`，rubric 显式声明"不以长度论优劣"。
4. **评估 Dataset** —— 15-20 条覆盖矩阵（deep 典型 / deep 边界 / quick / follow_up / 意图澄清），从历史 trace 捞取，Item Schema 含 input + expected_output。
5. **实验回归工作流** —— `evals/` 目录（与 src 平级，不侵入业务），`run_experiment` 跑全 Dataset，关联 prompt 版本，UI 对比基线。
6. **Judge 校准门禁** —— 上线前 Annotation Queue 人工打分，judge / 人工一致性 ≥ 80% 才可用；每月抽检防漂移。
7. **线上托管 Evaluator（第二阶段）** —— Langfuse 服务端同 rubric 采样评估（10-20%），Monitors 告警。

## Capabilities

### New Capabilities

- `evaluation`: Agent 输出质量的量化评估体系 —— 确定性评估器 + LLM-as-Judge + Dataset + 实验回归 + 校准 + 线上采样监控。

### Modified Capabilities

无。`citation_pass` 作为已有 Score 被 `evaluation` 复用，但其契约归属 `trace-observability`（上报行为）与本 capability（评估语义）分离，不修改 `trace-observability` 现有 requirement。

## Impact

- **新增代码**：`evals/` 目录（`conftest.py` / `env.py` / `dataset_seed.py` / `task.py` / `evaluators.py` / `run.py`），与 `src` 平级，不侵入业务代码。
- **Langfuse**：Score 从 1 个（`citation_pass`）扩至 6 个；新增 Dataset `a-share-analysis-v1`；新增 `langfuse-llm-as-a-judge` 环境标记，裁判成本独立核算。
- **依赖**：**强依赖 delta `agent-trace-content-fidelity`** —— Judge 的 `debate_quality` 读 `debate_history`、`decision_grounding` 读 `trade_decision` + 分析师结论、`consistency` 读各层 span output，这些内容的 trace 保真度由 delta 1 兜底；delta 1 未落地前 Judge 输入不完整。实施顺序：delta 1 → 本 delta。
- **协调**：与 `harden-llm-output-validation`（schema 校验）互补 —— 校验管"格式对不对"，评估管"质量好不好"，两者不重叠；与 `enable-deepseek-thinking-mode` 无冲突。
- **成本**：单轮实验（20 条 × 4 Judge）约 ¥0.5-1（deepseek-chat），< 主流程 5%；设计文档 §9 已预算。
- **风险**：中 —— Judge 冗长 / 位置偏置（对策：rubric 显式声明 + 校准）、Dataset 过拟合（对策：随 bad case 补库）、LLM 温度不可复现（对策：temperature=0 + 记录模型版本）。
