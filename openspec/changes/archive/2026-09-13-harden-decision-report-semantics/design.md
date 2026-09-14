# Design: harden-decision-report-semantics

## Context

管线现状（graph 顺序）：4 分析师 → 辩论 → RM → Trader（action+confidence）→ 风险辩论 → Risk Judge（action+confidence 修正方案）→ FM（仅 approve/reject/return + 理由）→ report（组装 final_report，FM 在其前）。

round5 校准实测暴露的问题（见 proposal）共同指向两个根因：**决策链的语义契约在 FM 层断裂**（上游都有 action/confidence，FM 只有流程动词），**报告结论层没有独立信号**（以审批复述收尾）。所有改动影响 judge 输入，实施窗口在 round5 校准收尾之后。

约束：
- 旧 trace 无 `focus_summary`、FM 无 action/confidence——评估兼容路径必须保留。
- FM 的 action 不是重新决策：Trader/Risk 已定方案，FM 的 action 是对最终方案的**确认性定性**，不得与裁决方向相悖（相悖即该 return/reject 而非另立方向）。

## Goals / Non-Goals

**Goals**
1. FM 决策可机读定性：approve 时必含 action+confidence，消除「approve 同意了什么」的推断成本。
2. FM 理由回归审批职责（风控一致性 + 论据矛盾），禁止投资背书。
3. 报告结论层有独立分析信号：judge 的 `report_conclusion` 取「研究聚焦」综合摘要而非审批复述。
4. 用户意图全链可见：focus 空缺时从 query 兜底；辩论/风控层注入 focus。

**Non-Goals**
- 不改 Trader/Risk Judge 输出契约（FM 对齐的对象形态）。
- 不改 citation 校验链路与分析师输出契约。
- 不在本 delta 内做 judge rubric 的再简化（rubric v2 的「评分前必读」段在 FM 语义落地后可缩减，属后续校准任务）。
- 不引入 LLM 意图澄清的新交互（兜底用规则提取，不新增反问轮次）。

## Decisions

### D1: FM action/confidence 的 schema 与必填策略

`FundManagerDecision` 新增：`action: str | None`（枚举同 TradeDecision.action）、`confidence: float | None`（0-1）。

- **approve 时 action+confidence 必填**（model validator 校验），reasoning 仍必填。
- **reject/return 时两者可为 None**：reject 是终止（无操作可定性），return 是退回（方案将重做，定性无意义）。
- 校验规则：approve 且 action 与 `final_trade_decision.action` 方向相悖时，**不硬拦截**（保留 FM 推翻权，与现有 approve 语义一致），但 report 拼装与 judge 材料中**并排展示两者**，让矛盾可见（交给 consistency 评分与人工审计，而非静默吞掉或硬失败）。

理由：硬拦截会把「FM 推翻」变成管线异常，违背 Layer V 仲裁定位；展示矛盾是评估体系的职责。

### D2: FM 理由边界用 prompt 约束，不加代码校验

`fund_manager.md` 决策语义段追加：approve 理由 SHALL 限定于「风控结论一致性、论据矛盾处理、执行前提」；SHALL NOT 对标的做方向性投资判断（如「适合长期价值投资」）——该类判断属研究层，FM 未见分析师报告无依据。不加代码级校验（LLM 自然语言无法可靠规则化），靠 rubric 与人工抽查监督（consistency rubric 已有「FM 理由与裁决逻辑相悖」扣分条款承接）。

### D3: 研究聚焦无条件生成 + state 落字段 + judge 变量改源

- `report.py`：`_build_focus_summary` 从 has_focus 分支放开为**无条件调用**；focus 为空时提示词固定为「综合各层产出写研究聚焦摘要」（不带关注点引导）。生成结果写入 `state["focus_summary"]`。
- `evals/extract.py`：`report_conclusion` 取值顺序：`state["focus_summary"]` → `extract_conclusion(final_report)`（回退，历史 trace 兼容）。
- 不改 `extract_conclusion` 本身（报告对用户展示的结论章节仍是审批章，用户可见报告结构不动；变的只是 judge 材料的「结论」信号源）。

理由：把「报告的分析结论」从「标题猜测」改为「数据源直取」，提取器不再依赖章节命名；标题猜测逻辑保留仅作回退。

### D4: focus 兜底在入口层做一次，用标签合成而非原 query 直灌

- 位置：`api.py` 深度分析入口，`req.focus` 为空时执行。
- 方法：对 query 跑 `parse_focus_tags` 同款词表，命中标签合成为弱 focus 文本（如「用户关注点: 估值、风险、中长期」）；零命中则不注入（保持现状，不硬造关注点）。
- 不把原始 query 全文注入分析师（避免诱导分析师越出领域事实职责，见 proposal 论证）；query 全文已进 report_relevance 的 judge 变量与 trace 观测，不丢失。

### D5: 辩论/风控层注入用既有 focus_hint 模式

`_build_debate_context` 与 `_build_risk_context` 各加 `focus_hint(state)`（与分析师/Trader/FM 同款一行注入）。不新增变量、不改 prompt 结构——辩论/风控 prompt 无需感知 focus 的存在，注入行作为 context 的一部分自然生效。

### D7: 结构化定性对战绩结算线的下游解锁（本 delta 不接线）

现状核实：`outcome/track_record/ingest.py` 落 predictions 只消费 `final_trade_decision`（Risk Judge 修正后 action 的方向映射 buy→long / sell→short / hold|watch→neutral）；**RM 的研究评级从未进入结算线**（model.py 的「看多/看空/中性」映射表仅用于查询过滤，非评级抽取）。本 delta 落地的 FM `action/confidence` 与 RM `rating/confidence` 结构化字段，为战绩化「研究观点与审批定性」解锁了低成本接入（新 prediction 来源或补充字段，无需自由文本评级抽取）。**接线不在本 delta 范围**——outcome 模块零改动，避免 delta 膨胀；作为后续独立 delta（届时需设计 RM 观点与交易 action 两类预测的结算语义区分：研究评级看方向，交易决策看盈亏）。

### 补记：辩论论点提取层补全（2026-09-10，已直接修复）

校准实测发现 `DebateMessage.key_arguments`（LLM 已按 prompt 结构化输出、质量良好）被 `_summarize_debate` 拼装时全程丢弃；且辩论总量超 4096 字节时整体挖心截断连【bear】标签一起切掉（judge 评「逐条交锋」看不到交锋过程）。两处已随校准直接修复（非本 delta 范围，属既有能力提取层补课）：①按消息边界截断（每条 800 字节）；②key_arguments 以「论点: …」行前置到每条发言开头（上限 400 字节）——正文被截时每轮论点骨架仍全数在场，judge 的交锋对照有锚点。与 analyst_reports 的 per-agent 截断修复同族。

### D6: 兼容与重评边界

- 旧 trace（无 focus_summary、FM 无 action）：评估回退路径覆盖（D3 回退 + judge 变量序列化对缺字段容忍）。
- 实施后的重评范围：FM 输出结构变化影响全部维度的 `fund_manager_decision` 变量序列化；`report_conclusion` 变化影响 consistency。**consistency 与 decision_grounding 须全量重评**；report_relevance/debate_quality 的 judge 变量不含这两者，无需重评。
- round5 盲标表（v4）与本 delta 实施前产生的 judge 分保持既有口径，作为「改动前基线」归档，不做混合对比。

## Risks / Trade-offs

- FM action 必填可能推高 FM 输出格式失败率（LLM 漏字段）→ 沿用 `FundManagerDecision` 现有强校验 + 解析重试路径，失败即中断管线（与「非法 decision 值中断」同级，显式失败好过静默）。
- 研究聚焦无条件生成增加每次分析 1 次 LLM 调用（约 2-3k token）→ 相对单次分析约 14 万 token 的成本可忽略。
- focus 兜底的词表覆盖有限（「投资价值」「现金流」等未命中标签的问法拿不到兜底）→ 词表与 parse_focus_tags 共享演进，不追求一次完备。

## Migration Plan

1. 实施顺序：D1（模型+routing+report 展示）→ D2（prompt）→ D3（report+extract）→ D4（入口兜底）→ D5（注入）——依赖方向单一，无环。
2. 每步先失败测试后实现（TDD），交互面（前端 FM 展示）若涉及走 E2E 门禁。
3. 全部落地后重跑 dataset 实验 → consistency/decision_grounding 重评 → 对照 round5 基线归因。
