# 托管 Evaluator 配置手册(第二阶段)

**适用阶段**: agent-evaluation-suite 第二阶段 —— 线下实验回归完成、Judge 校准定稿(一致性 ≥ 80%)后,在 Langfuse UI 配置托管 Evaluator(Managed Evaluator),对线上 trace 持续评分。

**前置条件**:
- Langfuse 自托管实例可访问(默认 http://localhost:3000)
- 线下校准一致性 ≥ 80%(见 `tests/validation/2026-08-12-agent-evaluation-suite-validation.md` 校准栏)—— **达标前不得开启线上阻塞**
- Delta 1 span 保真已生效(变量映射依赖 trace span 路径)

**核心原则**: 线下线上一把尺(design 决策 2)—— 线上 rubric 必须与线下 `evals/judges.py: RUBRICS` 逐字一致,裁判模型同为 `deepseek-chat`。

---

## 1. 创建 Managed Evaluator(4 个 Judge 各建一条)

路径: Langfuse UI → **Evaluators** → **New Managed Evaluator**

每个维度创建一条 Evaluator,rubric 文本从 `evals/judges.py` 的 `RUBRICS` dict **原样复制**(含末尾 JSON 约束与「不以篇幅长短论优劣」):

| Evaluator 名 | rubric 来源 | 裁判模型 |
|---|---|---|
| `report_relevance` | `RUBRICS["report_relevance"]` | `deepseek-chat` |
| `debate_quality` | `RUBRICS["debate_quality"]` | `deepseek-chat` |
| `decision_grounding` | `RUBRICS["decision_grounding"]` | `deepseek-chat` |
| `consistency` | `RUBRICS["consistency"]` | `deepseek-chat` |

注意:
- 裁判输出格式要求与线下一致: `{"score": <1-5>, "reason": "<一句话理由>"}`(rubric 尾部已含此约束,勿删改)。
- 修改线上 rubric 时必须同步改 `evals/judges.py: RUBRICS` 并重新跑线下校准,禁止只改一边。

## 2. 变量映射表(变量名 → trace span 路径)

变量清单与线下 `evals/extract.py: extract_judge_vars` 的 9 个 judge 变量一一对应;span 路径依赖 Delta 1 span 保真(trace 节点名与管线节点一致):

| 变量名 | trace span 路径 | 使用维度 |
|---|---|---|
| `query` | trace input / metadata `focus` | report_relevance |
| `report` | 末节点输出 `final_report` | report_relevance |
| `report_conclusion` | `final_report` 结论章节(## 结论/总结/交易建议;缺失取末尾 500 字符,见 `evals/extract.py: extract_conclusion`) | consistency |
| `analyst_reports` | 4 个分析师节点 span 输出汇总(summary/conclusion 优先) | decision_grounding, consistency |
| `debate_history` | Bull/Bear 辩论节点 span 输出 `debate_history` | debate_quality |
| `research_manager_decision` | Research Manager 节点 span 输出 `research_manager_conclusion` | decision_grounding, consistency |
| `trade_decision` | Trader 节点 span 输出 `final_trade_decision`(JSON) | decision_grounding |
| `risk_judgment` | Risk Judge 裁决(`final_trade_decision` + `risk_debate_history` 尾部 2 条) | consistency |
| `fund_manager_decision` | Fund Manager 节点 span 输出 `fund_manager_decision` | consistency |

若 Langfuse UI 的变量映射能力无法直接表达「章节提取/汇总」类派生变量(`report_conclusion`/`analyst_reports`/`risk_judgment`),则该维度保留线下实验路径,不上托管——禁止为迁就 UI 能力简化 rubric 造成线下线上不一致。

## 3. 采样率

- 初值 **10-20%**(控制裁判 LLM 成本);观察 1-2 周 score 分布稳定后再评估是否上调。

## 4. 过滤器

- `mode=quick` 的 trace **只挂 `report_relevance`**(quick 无辩论/决策层,其余 3 维度无输入,与线下 `evals/run.py: _JUDGE_DEEP_ONLY` 过滤口径一致)。
- `mode=deep` 的 trace 挂全部 4 个维度。

## 5. Monitors 告警

- 配置 Score 均值窗口骤降告警 → webhook 通知。
- 建议阈值(初值,随校准数据调整): 任一维度 7 日滑动均值相对前一周下降 ≥ 1 分,或均值 < 3 分时触发。

## 6. 校准前置(硬性门禁)

- **线下一致性 ≥ 80% 前不得开启线上阻塞**(score 仅观测,不拦截/不影响业务链路)。
- 校准流程见 `openspec/changes/agent-evaluation-suite/` spec Requirement「Judge 校准与人工标注」:抽 20-30 条人工打分,与 judge 输出比对一致性;校准报告回填验证报告。
- 托管 Evaluator 上线后首月每周抽查一次线上 score 与线下复评的一致性,防线上漂移。

---

## 变更纪律

- rubric / 裁判模型 / 采样率的任何修改都属行为变更:同步修改 `evals/judges.py` 与本手册,重跑线下校准,并更新验证报告。
- 本手册与 `evals/judges.py: RUBRICS` 不一致时,以代码为准并立即修正文档。
