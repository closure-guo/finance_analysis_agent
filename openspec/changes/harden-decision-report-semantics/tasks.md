# Tasks: harden-decision-report-semantics

> **实施前置门禁**：本 delta 全部实施工作须等 round5 judge 校准收尾（53 行盲标 + measure 报告归档）后开始；实施完成后须按 §6 重评。开始实施前确认四个既有 delta（add-agent-readable-conclusion / harden-evaluation-dataset-sampling / add-golden-set-assertion-types / harden-eval-implementation-decoupling）已 archive。

## 1. FM 决策结构升级（D1，agent-node-contracts）

- [ ] 1.1 失败测试：`FundManagerDecision` 新增 `action`/`confidence` 可选字段；approve 缺任一字段 → ValidationError；reject/return 缺省 → 校验通过（tests/test_models.py）
- [ ] 1.2 实现 `src/finance_agent/models.py` 的 FundManagerDecision 扩展 + approve 必填 validator（沿用 _reasoning_not_blank 模式）
- [ ] 1.3 失败测试 + 实现：FM prompt（fund_manager.md）输出格式段加 action/confidence 要求与语义说明（action=对最终方案的操作定性，非赞成/否决票）
- [ ] 1.4 `nodes/fund_manager.py` / `routing.py`：确认 approve 的 action 与裁决相悖时不拦截（现有强校验仅对 decision 枚举），跑通 return 循环回归测试
- [ ] 1.5 失败测试 + 实现：report 节点「基金经理决策」章节并排展示 FM action/confidence 与裁决 action（ADR-0011 标注保留）
- [ ] 1.6 失败测试 + 实现：`evals/extract.py` 的 `_serialize_decision`/`fund_manager_decision` 变量含 action/confidence（存在时）
- [ ] 1.7 失败测试 + 实现：RM 结构化输出——`research_manager.py` 解析 JSON（reasoning/rating/confidence），`state["research_manager_conclusion"]` 改为评级前置拼装，另存 `research_manager_rating`/`research_manager_confidence`；解析失败降级为自由文本（不中断，降级可观测）
- [ ] 1.8 失败测试 + 实现：RM prompt（research_manager.md）改 JSON 输出模板（键序 reasoning 在前 rating 在后，保持先推理后结论生成顺序）；随 §2.3 一并 deploy_prompts
- [ ] 1.9 失败测试：Trader context 与 `research_manager_decision` judge 变量所见文本为评级前置拼装（解析 RM 结论的旧逻辑若存在须移除，单一权威点）
- [ ] 1.10 失败测试 + 实现：辩论 context 编号呈现——`_build_debate_context` 各历史发言以「论点: ①…」编号行前置（取 key_arguments）
- [ ] 1.11 失败测试 + 实现：`DebateMessage` 新增可选 `rebuttal_to: list[int]`；bull/bear prompt 输出格式加 rebuttal_to 与「回应对方N」标注要求（随 §2.3 一并 deploy_prompts）
- [ ] 1.12 失败测试 + 实现：交锋覆盖率计算（各轮 rebuttal_to 并集 / 对方论点总数，纯函数）并进入 debate_quality judge 材料（evals/extract.py 拼装时并列呈现双方论点编号）

## 2. FM 理由职责边界（D2，agent-prompt-contracts）

- [ ] 2.1 `prompts/fund_manager.md` 决策语义段追加理由边界条款：限定风控一致性/论据矛盾/执行前提，禁止方向性投资背书（含反例表述）；与 1.3 合并为一次 prompt 变更
- [ ] 2.2 失败测试：加载 fund_manager.md 断言边界条款与反例存在（tests/ 对应 prompt 契约测试）
- [ ] 2.3 执行 `uv run python scripts/deploy_prompts.py` 发布 prompt（否则 eval 门禁拒绝运行）

## 3. 报告结论层重构（D3，agent-evaluation-suite）

- [ ] 3.1 失败测试：report 节点 focus 为空时仍生成聚焦摘要并写 `state["focus_summary"]`（tests/nodes/test_report.py）
- [ ] 3.2 实现 `nodes/report.py`：`_build_focus_summary` 无条件调用；focus 空时固定提示词；`generate_report` 返回 `focus_summary` 键
- [ ] 3.3 失败测试 + 实现：`evals/extract.py` 的 `report_conclusion` 取值顺序 `state["focus_summary"]` → 回退 `extract_conclusion(final_report)`；补历史 trace 兼容用例
- [ ] 3.4 验证 consistency judge 材料中【最终报告结论章节】为聚焦摘要文本、非 FM 复述（用缓存 fixture 或既有 trace fixture 断言）
- [ ] 3.5 失败测试 + 实现：deep 报告的 `report` judge 变量改为结构化拼装（研究聚焦 + 各分析师摘要 + RM 结论 + 交易决策要点 + FM 决策，剔除图片 markdown 引用），替代 final_report 全文 head/tail 截断——实证 4f58faf7：4096 截断后 judge 仅见图表路径与审批章，幻觉推断「全面覆盖」恒 5 分
- [ ] 3.6 失败测试 + 实现：decision_grounding rubric 模板加【多空辩论记录】{{debate_history}}（rubric v4）+ material DIMENSION_SECTIONS 同步；实证 2fd1ee6d：交易决策 7 条 evidence_refs 有 2 条 debate_bear 来源，judge 输入无辩论记录无法核对（rubric 要求核对未提供的材料，自相矛盾）；实施后 decision_grounding 全量重评
- [ ] 3.7 失败测试 + 实现：标注材料人类可读渲染——【交易决策】等节的转义 JSON 解析为人读格式（action/置信度/仓位/论据来源分布/理由分行），解析失败保持原文；展示层渲染不改变信息内容（同口径保持）
- [ ] 3.8 report_relevance rubric 口径修订（v3）：「切题=回答了用户的问题」——覆盖维度但回避用户所问的直接决策问题 SHALL ≤3；Safety 约束下如实说明约束并给可行答案 SHALL 视为已回答；失败测试锁定新口径措辞 + decision_grounding 式全量重评报告验证分歧收敛

## 4. 用户意图贯穿（D4/D5，user-intent-propagation）

- [ ] 4.1 失败测试：query 命中标签时入口合成弱 focus（「分析…适不适合作为长期持有股买入」→ mid_long_term 等）；零命中 focus 保持空；query 全文不进分析师 context
- [ ] 4.2 实现 `api.py` 深度分析入口的兜底提取（复用 parse_focus_tags 词表）
- [ ] 4.3 失败测试 + 实现：`_build_debate_context` 与 `_build_risk_context` 注入 `focus_hint(state)`；focus 空时零注入回归用例

## 5. 集成验证

- [ ] 5.1 `uv run pytest` 全绿 + `uv run ruff check` + `uv run mypy` 通过
- [ ] 5.2 本地跑 1 条深度分析（真实 LLM）：确认 FM 输出含 action/confidence、报告含研究聚焦与并排定性、辩论/风控 context 含关注点行（Langfuse trace 人工核对）
- [ ] 5.3 若涉及前端 FM 展示：E2E 门禁通过（交互类变更红线）；无前端改动则本项标注「不适用」

## 6. 评估收口（实施后）

- [ ] 6.1 重跑 dataset 实验（baseline 池），确认 judge 分正常落库、无 input_missing/judge_parse_failed 异常
- [ ] 6.2 consistency 与 decision_grounding 维度重评（FM 序列化 + report_conclusion 变更影响面）；report_relevance/debate_quality 无需重评（judge 变量未变）
- [ ] 6.3 对照 round5 基线归档对比报告（tests/validation/ 或 docs/evals/），rubric v2「评分前必读」段的简化评估（可简化则 rubric 升 v3 走独立校准）
