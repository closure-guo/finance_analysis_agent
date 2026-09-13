# Proposal: harden-decision-report-semantics

## Why

round5 judge 校准期间（2026-09-09/10）连续实测发现决策链与报告层的 5 个结构性语义问题，它们共同导致：judge 与人工对 consistency/decision_grounding 的评分依据失真（judge 拿到的是复述与残缺语义）、用户意图无法贯穿流水线、FM 决策的可读性依赖猜理由。这 5 个问题相互同源（决策语义未定义清楚、报告结论层缺独立信号、用户意图只覆盖部分层），须作为一组语义对齐变更统一处理。

实证锚点（全部来自 trace 2fd1ee6d / 43aaa1ea 等实测）：

1. FM 只有 `approve/return/reject` + 自由理由，无操作性结论（action/confidence）；「approve 到底同意了什么」需通读理由推断（consistency rubric v2 被迫写「评分前必读」语义段来补偿）。
2. FM 理由漂移投资背书腔（「风险收益特征与长期价值投资逻辑相符」），越出「审批风控」职责，且 FM 根本看不到分析师报告——背书无信息支撑。
3. 最终报告以「基金经理决策」章节收尾（report 节点在 FM 后从 state 拼装），judge 变量 `report_conclusion` 提取到的是 FM 复述，与【Fund Manager 最终决策】逐字重复；真正承载分析综合的「研究聚焦」章节被提取规则跳过，且仅 focus 非空时生成。
4. focus（意图澄清产物）为空时，原始 query 的意图关键词全链丢失——通用问法下没有任何层知道用户问的角度。
5. 辩论层（bull/bear）与风险层（三方辩论 + Risk Judge）context 不含 focus_hint：用户问「适不适合长期持有」，辩论仍辩通用多空、风控仍用单日 VaR(95%) 审长期持有风险（期限错配）。

**实施前置条件**：本 delta 全部改动都影响 judge 输入与评分可比性，**实施须等 round5 校准收尾（53 行盲标 + measure 报告）后进行**；实施后须对受影响维度重评。

## What Changes

- **FM 决策结构升级**：`FundManagerDecision` 新增 `action`（buy/hold/watch/sell 等，与 TradeDecision.action 同枚举）与 `confidence`（0-1）字段——FM 在 approve 时必须给出对最终方案的操作定性；reject/return 时 action 可为空但须说明。**BREAKING**（下游消费 FM 输出的契约面变化：routing/report/judge 变量/前端）。
- **RM 结构化评级输出**：Research Manager 从自由文本改为结构化 JSON（reasoning + rating + confidence），JSON 键序保持「先推理后结论」的生成顺序；消费端由代码把评级前置（state 结论字符串、报告章节、Trader context、judge 变量），解析失败降级为自由文本不中断。RM 是决策链最后一个无结构化结论的节点，补齐后「每个决策层 = 结构化结论 + 代码前置展示」全链统一。
- **辩论交锋结构化引用**：以既有 key_arguments 为编号锚点——辩论 context 编号呈现对方论点、`DebateMessage` 新增 `rebuttal_to`（回应的对方论点编号）、交锋覆盖率成为零 token 确定性指标；治理「引用靠现场转述（曲解不可检测）+ 交锋覆盖不可计算」的结构弱点。Bull/Bear 先行，风险辩论三方同构跟进。
- **FM 理由职责边界**（prompt `fund_manager.md`）：approve/return/reject 理由限定在「风控结论一致性 + 论据矛盾处理」，禁止方向性投资背书（不引入分析师层之外的标的优劣判断）。
- **报告结论章节重构**：report 节点无条件生成「研究聚焦」综合摘要（focus 为空时用固定提示词生成通用摘要），存入 state（`focus_summary`）；judge 变量 `report_conclusion` 改为优先取 `focus_summary`，缺失时回退现有 `extract_conclusion(final_report)`（历史 trace 兼容）。
- **focus 兜底**：意图澄清未收集到 focus 时，从原始 query 提取关注点关键词作为弱 focus（规则提取，复用 `parse_focus_tags` 词表方向），保证用户角度全链可见。
- **辩论层与风险层注入 focus**：`_build_debate_context` 与 `_build_risk_context` 加入 `focus_hint(state)`，辩题向用户角度收敛、风险谱向用户期限/关注维度倾斜。
- **report_relevance 口径修订（rubric v3）**：round5 校准实证（13 条 Δ4 分歧全部「人工 1 vs judge 5」）——judge 以「主题相关」口径打分（覆盖相关维度即切题），人工以「问题解答」口径（「茅台现在能买吗」不给买/不买结论=未回答）。rubric SHALL 明确「切题=回答了用户的问题」：覆盖维度但回避用户所问的直接决策问题时 SHALL ≤3；因 Safety 约束无法给出直接结论时，如实说明约束并给出约束下的可行答案 SHALL 视为已回答。

## Capabilities

### New Capabilities

- `user-intent-propagation`: 用户意图（focus/query 兜底）在流水线各层的注入契约——兜底提取规则、辩论层与风险层的注入要求、focus 空缺时的降级行为。

### Modified Capabilities

- `agent-node-contracts`: FM 决策结构新增 action/confidence 字段的校验、回退与下游消费契约（routing/report 对 action 的使用）；RM 结构化评级输出（reasoning/rating/confidence）与评级前置拼装契约、解析失败降级。
- `agent-evaluation-suite`: judge 变量 `report_conclusion` 的取值来源变更（`focus_summary` 优先 + 回退），consistency 维度材料中【最终报告结论章节】的语义从「审批复述」变为「分析综合」。
- `agent-prompt-contracts`: `fund_manager.md` 理由职责边界条款（禁止投资背书、approve 须含操作定性）。

## Impact

- **代码**：`src/finance_agent/models.py`（FundManagerDecision）、`nodes/fund_manager.py`、`prompts/fund_manager.md`、`nodes/report.py`（聚焦摘要无条件生成 + state 落字段）、`nodes/debate.py`、`nodes/risk.py`（focus_hint）、`api.py`（focus 兜底提取入口，或 nodes 层）、`routing.py`（FM return 循环对 action 的处理）、`evals/extract.py`（report_conclusion 取值）。
- **评估**：FM 输出结构变更影响全部下游 judge 变量（`fund_manager_decision` 序列化格式变化）；`report_conclusion` 变更影响 consistency 维度材料与评分。实施后须重跑实验并对 consistency/decision_grounding 重评（rubric v2 的「评分前必读」段届时可大幅简化）。
- **前端**：FM 决策展示（若有读取 reasoning 的 UI，须兼容 action/confidence 新字段）。
- **战绩结算线（下游解锁，本 delta 不接线）**：`outcome/track_record` 当前落 predictions 只消费 `final_trade_decision`（Risk Judge 修正后 action），RM 评级从未进入结算。FM `action/confidence` 与 RM `rating/confidence` 结构化落 state 后，研究观点与审批定性的战绩化（新增 prediction 来源或补充字段）成为低成本接入——无需自由文本评级抽取。接线属后续独立 delta。
- **不改动**：trader/risk_judge 的输出契约（它们已有 action/confidence，是 FM 对齐的目标形态）；citation 校验链路；`outcome/track_record` 模块（本 delta 仅解锁、不改其代码）。
