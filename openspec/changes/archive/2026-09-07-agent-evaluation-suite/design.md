## Context

### 现状

- **唯一 Score**：`citation_pass`（`nodes/citation_node.py:54-60`），boolean，trace 级上报；只测客观数据重算。
- **主观质量零评估**：辩论质量、决策依据、跨层一致性、报告切题度均无 Score；`harden-llm-output-validation` 显式决定不上报枚举违约 Score（`design.md:120`），仅靠 WARNING 日志。
- **无 eval 框架**：`tests/fixtures/` 只有原始数据（输入侧），无标注答案；无 LLM-as-Judge；ADR-0010:126 推迟为"未来 Eval Pipeline"。
- **prompt 变更无回归**：ADR-0016 自承"无 A/B 实验能力"，迁移只是"为 L2 Experiment 铺路"；`prompts/loader.py` 只有 production label，换版本靠改 label + 重启。
- **设计文档已存在**：`docs/design/Langfuse评估体系设计文档.md` 完成 12 章设计，本 delta 将其固化为 spec 契约并对若干瑕疵补全（见决策 4、5）。

### 约束

- **TESTING=1 stub 不能用于 Judge 校准**：stub 返回固定 JSON（`_llm_utils.py:160-179`），Judge 评估必须跑真实 LLM；Dataset 实验以 `@live` 标记 nightly 跑。
- **AKShare 数据时效**：历史 trace 的 expected 数值会随时间失效，对策：expected_output 只断言结构性内容（章节、ticker），不断言具体数值（设计文档 §11 已列）。
- **Judge 输入依赖 trace 保真**：`debate_history` / `trade_decision` / 各层 span output 的完整性由 delta `agent-trace-content-fidelity` 兜底，本 delta 假设其已落地。
- **单 worker**：实验在离线跑，不涉及 StreamRegistry；线上托管 Evaluator 在 Langfuse 服务端，不占应用 worker。

## Goals / Non-Goals

**Goals:**

- 6 个 Score（2 确定性 + 4 Judge）落地，覆盖结构 / 切题 / 辩论 / 决策依据 / 一致性五维。
- 15-20 条 Dataset 首版建库，`evals/run.py` 可一键跑实验并出对比表。
- Judge 上线前必须经人工校准（≥ 80% 一致性），rubric 可迭代。

**Non-Goals:**

- **不做决策事后效果评估**（forward return / 跑赢基准）—— 属 delta `decision-outcome-tracking`，本 delta 的 `decision_grounding` 只评逻辑一致性（论据有无前文支撑），不评决策对错。
- **不做 CI 质量门禁的强阻塞** —— 实验结果进 CI 仅作参考显示，是否阻塞 PR 留团队策略（设计文档 §10 S6 标"可选"）。
- **不改业务管线代码** —— `evals/` 与 src 平级，业务零侵入；`citation_node.py` 不动。
- **不覆盖 quick 模式的辩论 Judge** —— quick 模式无辩论，`debate_quality` 仅 deep 模式跑（设计文档 §7 过滤器）。

## Decisions

### 决策 1：三层分工原则（沿用设计文档 §2）

**选择**：确定性评估（代码 / 零 token）优先，查不了的才用 Judge（贵 / 需校准），存疑的进人工 Annotation。"能用代码查的用代码"。
**理由**：`citation_pass` / `section_coverage` / `ticker_match` 确定性可进 CI、零成本、可重算；Judge 只用于主观质量。混用会让"LLM 判 LLM 数字对错"成为脆弱链（ADR-0010:126 原话）。
**备选**：全部用 Judge —— 否决，成本高一个量级且不可重算。

### 决策 2：线下实验与线上托管用同一套 rubric

**选择**：`evals/evaluators.py` 的 Judge 与 Langfuse 服务端托管 Evaluator 配置同一套 rubric 文本、同一裁判模型（`deepseek-chat`）、同一变量映射。
**理由**：保证"上线前测的"和"上线后看的"是同一把尺子，否则线上漂移信号无法对照线下基线。
**备选**：线上线下不同 rubric —— 否决，对照失去意义。

### 决策 3：Judge Score 控制在 4 个

**选择**：`report_relevance` / `debate_quality` / `decision_grounding` / `consistency`，每个有明确 rubric，不为评而评。
**理由**：设计文档 §3.1 原则；Judge 越多校准成本越高、越易冗余。
**备选**：再加"风险覆盖度""幻觉率"等 —— 否决，首版够用，按 bad case 驱动后续追加。

### 决策 4：补全 `consistency` rubric（对原设计文档 §4.4 的补全）

**选择**：原设计文档 §4.4 的 consistency rubric 不完整（缺完整 prompt 模板与变量映射），本 delta 补全为：
```
你是投资报告一致性评审专家。
【分析师章节结论】{{analyst_reports}}
【Research Manager 结论】{{research_manager_decision}}
【Risk Judge 裁决】{{risk_judgment}}
【Fund Manager 最终决策】{{fund_manager_decision}}
【最终报告结论章节】{{report_conclusion}}
评估各层结论的一致性：
5 = 各层结论完全一致，无静默推翻
4 = 基本一致，个别表述差异但不影响方向
3 = 存在不一致但已显式说明理由
2 = 存在未说明的结论冲突
1 = 明显自相矛盾（如 Fund Manager 批准与 Risk Judge 否决相悖）
只输出 JSON: {"score": <1-5>, "reason": "<一句话理由>"}
特别关注：Fund Manager 结论是否与 Risk Judge 裁决一致；报告结论章节是否与分析师章节一致。
不以报告长度论优劣。
```
变量映射：`analyst_reports` / `research_manager_decision` / `risk_judgment` / `fund_manager_decision` / `report_conclusion` 从 state / span output 读（依赖 delta 1 的 span 内容保真）。
**理由**：spec 必须可执行，rubric 不能留半截。
**备选**：留 Open Question 后补 —— 否决，会阻塞校准与实施。

### 决策 5：`section_coverage` 匹配改用语义词典（修正设计文档 §6.2 的脆弱匹配）

**选择**：设计文档 §6.2 的 `s not in output["report"]` 字符串匹配脆弱（中文"偿债能力"写成"偿债分析"即漏判）。本 delta 改为：每个必备章节配一组同义词（如"偿债能力" → `["偿债能力", "偿债分析", "债务分析", "solvency"]`），命中任一即算覆盖。
**理由**：中文报告表述差异大，裸 `in` 匹配误报率高，会污染 section_coverage Score。
**备选**：嵌入向量语义匹配 —— 否决，首版过重，同义词词典够用且可解释。

### 决策 6：Judge 输出强约束 JSON

**选择**：所有 rubric 末尾强制"只输出 JSON: {"score": <1-5>, "reason": "<一句话理由>}"；解析失败按重试一次 → 失败标 score=null（不阻塞实验，但计入 judge 失败率）。
**理由**：复用 `nodes/_llm_utils.py` 的 `parse_json_response`；score=null 在校准时单独看，避免坏数据污染均分。
**备选**：宽松解析取首个数字 —— 否决，易取错（reason 里也可能有数字）。

## Risks / Trade-offs

- **[Judge 冗长 / 位置偏置]** → rubric 显式声明"不以长度论优劣"；校准时重点检查（设计文档 §8）。
- **[Dataset 过拟合]** → 随线上 bad case 持续补库；定期换一批（设计文档 §11）。
- **[LLM 温度不可复现]** → 评估用 `temperature=0`；记录模型版本到 trace metadata（依赖 delta 1 的 prompt 元数据）。
- **[AKShare 数值时效致 expected 失效]** → expected_output 只断言结构性内容（章节、ticker），不断言具体数值。
- **[Judge 输入依赖 delta 1]** → 实施顺序锁死：delta 1 先行；若 delta 1 延期，本 delta 的 Judge 先只跑 `report_relevance`（仅需最终报告，不依赖 span 内部）。
- **[follow_up 模式依赖前置会话]** → 该模式 case 单独建 session fixture，或首版跳过（设计文档 §11）。

## Open Questions

- CI 门禁是否强阻塞 PR —— 留团队策略，首版仅显示不阻塞。
- 线上托管 Evaluator 采样率初值 —— 设计文档建议 10-20%，上线后按成本回调。
- `consistency` 的变量 `report_conclusion` 是否需要独立 render 节点产出 —— 取决于最终报告结构，实施时确认。
