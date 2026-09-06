# hosted evaluator 模板快照（enable-hosted-evaluator 降级治理）

> 背景（2026-09-04 取证）：自托管 Langfuse 3.205.1 无 evaluator 公共 API，
> managed evaluator 仅能 UI 配置、无法脚本化/版本化。本文件是模板的**手工快照**：
> 每次在 Langfuse UI 修改 evaluator 配置后，回填此文件（等效 prompt-deploy 纪律）。

## 状态

- [ ] 尚未在 UI 配置 evaluator
- 四个维度 = 四个独立 evaluator（Langfuse 一个 evaluator 只挂一条模板），各建一条
- 评分制：UI 中把分数范围设为 **1-5**（离线 rubric 为 1-5 分制）
- 采样率：各 10%
- 变量映射：创建时把 `{{变量}}` 映射到 trace 字段（见每维「映射」说明；
  report/辩论/决策数据在深度管线 trace 的 output 与 metadata 中）

## 模板 1：report_relevance（报告切题度）

映射：`{{query}}` ← trace input（用户查询）；`{{report}}` ← 报告正文（output/metadata.report_markdown）

```text
你是投资研究报告评审专家。
【用户查询】{{query}}
【分析报告】{{report}}
评估报告对查询的切题度:
5 = 完全切题,紧扣查询意图展开
4 = 基本切题,少量无关内容
3 = 部分切题,有显著偏离或答非所需的段落
2 = 大部分答非所问,仅边缘相关
1 = 完全答非所问
只输出 JSON: {"score": <1-5>, "reason": "<一句话理由>"}
不以篇幅长短论优劣。
```

## 模板 2：debate_quality（辩论质量）

映射：`{{debate_history}}` ← 多空辩论记录（trace 内 debate history / metadata）

```text
你是投资辩论质量评审专家。
【多空辩论记录】{{debate_history}}
评估辩论的实质交锋程度:
5 = 双方逐条回应对方论点且引用具体证据(数据/事实)
4 = 有实质交锋,证据基本充分,个别论点空泛
3 = 有交锋但多为立场声明,证据引用不足
2 = 交锋形式化,双方自说自话
1 = 单方输出或内容空洞,无实质辩论
只输出 JSON: {"score": <1-5>, "reason": "<一句话理由>"}
不以篇幅长短论优劣。
```

## 模板 3：decision_grounding（决策接地，rubric v3）

映射：`{{analyst_reports}}` ← 分析师结论汇总；`{{research_manager_decision}}` ← RM 结论；
`{{trade_decision}}` ← 交易决策（含 evidence_refs 时逐条核对）

```text
你是投资决策依据评审专家。
【分析师结论】{{analyst_reports}}
【Research Manager 结论】{{research_manager_decision}}
【交易决策】{{trade_decision}}
评估交易决策的论据是否有前文支撑:
若交易决策含 evidence_refs（结构化论据引用，每项含 claim 与 source），逐条核对：
- claim 的数值/事实能在对应 source（technical/macro/fundamental/sentiment/debate_bull/debate_bear/research_manager）的结论中找到出处，
  且 reasoning 的主要论据都能在 evidence_refs 中找到对应项 → 4-5 分；
- 语义一致性核对：论据表述的指标术语、期次、方向须与所引数值语义一致——
  数值有出处但术语张冠李戴（毛利率写成净利率）、期次错位（年报值说成季度值）、
  方向失当（数值下降表述为「改善」、行业垫底表述为「行业领先」）属解读失当，
  不得仅因数值有出处给高分 → 降至 2-3 分；
- source 与论据对不上、claim 数值在来源中不存在（无中生有）、或 evidence_refs 缺失
  reasoning 中大量论据的引用 → 1-2 分。
无 evidence_refs 时按以下原规则从自由文本推断（不因缺字段报错）:
5 = 决策的每条论据都能在分析师结论/辩论结论中找到出处
4 = 主要论据有出处,个别细节无明确支撑
3 = 部分论据有出处,存在未论证的跳跃
2 = 论据与前文关联薄弱,或与前文结论有张力未解释
1 = 决策与前文矛盾,或论据无中生有
只输出 JSON: {"score": <1-5>, "reason": "<一句话理由>"}
不以篇幅长短论优劣。
```

## 模板 4：consistency（各层结论一致性）

映射：`{{analyst_reports}}` ← 分析师章节；`{{research_manager_decision}}` ← RM 结论；
`{{risk_judgment}}` ← Risk Judge 裁决；`{{fund_manager_decision}}` ← FM 最终决策；
`{{report_conclusion}}` ← 报告结论章节

```text
你是投资报告一致性评审专家。
【分析师章节结论】{{analyst_reports}}
【Research Manager 结论】{{research_manager_decision}}
【Risk Judge 裁决】{{risk_judgment}}
【Fund Manager 最终决策】{{fund_manager_decision}}
【最终报告结论章节】{{report_conclusion}}
评估各层结论的一致性:
5 = 各层结论完全一致,无静默推翻
4 = 基本一致,个别表述差异但不影响方向
3 = 存在不一致但已显式说明理由
2 = 存在未说明的结论冲突
1 = 明显自相矛盾(如 Fund Manager 批准与 Risk Judge 否决相悖)
特别关注:Fund Manager 结论是否与 Risk Judge 裁决一致;报告结论章节是否与分析师章节一致。
只输出 JSON: {"score": <1-5>, "reason": "<一句话理由>"}
不以篇幅长短论优劣。
```

## 快照（UI 配置后回填）

```yaml
# 每建一个 evaluator 回填一段；configId 供轮询脚本 --config-id 用
- name: <evaluator 名>
  configId: <UI 中的 config id>
  采样率: 10%
  模型: <judge 使用的模型>
  模板: <与上方一致则注「同模板 N」；有改动则粘贴 UI 实际内容>
```

## 口径对齐

- hosted 分数与离线 judge 对同一 trace 的打分 MAE 阈值 ≤ 1.0
- 超阈值 → 统一口径（以人工校准结论为准，见 add-judge-human-calibration）
