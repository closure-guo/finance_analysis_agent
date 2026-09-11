# Tasks: harden-decision-report-semantics

> **实施前置门禁**：本 delta 全部实施工作须等 round5 judge 校准收尾（53 行盲标 + measure 报告归档）后开始；实施完成后须按 §6 重评。开始实施前确认四个既有 delta（add-agent-readable-conclusion / harden-evaluation-dataset-sampling / add-golden-set-assertion-types / harden-eval-implementation-decoupling）已 archive。

## 1. FM 决策结构升级（D1，agent-node-contracts）

- [x] 1.1 失败测试：`FundManagerDecision` 新增 `action`/`confidence` 可选字段；approve 缺任一字段 → ValidationError；reject/return 缺省 → 校验通过（tests/test_models.py）
- [x] 1.2 实现 `src/finance_agent/models.py` 的 FundManagerDecision 扩展 + approve 必填 validator（沿用 _reasoning_not_blank 模式）
- [x] 1.3 失败测试 + 实现：FM prompt（fund_manager.md）输出格式段加 action/confidence 要求与语义说明（action=对最终方案的操作定性，非赞成/否决票）
- [x] 1.4 `nodes/fund_manager.py` / `routing.py`：确认 approve 的 action 与裁决相悖时不拦截（现有强校验仅对 decision 枚举），跑通 return 循环回归测试
- [x] 1.5 失败测试 + 实现：report 节点「基金经理决策」章节并排展示 FM action/confidence 与裁决 action（ADR-0011 标注保留）
- [x] 1.6 失败测试 + 实现：`evals/extract.py` 的 `_serialize_decision`/`fund_manager_decision` 变量含 action/confidence（存在时）
- [x] 1.7 失败测试 + 实现：RM 结构化输出——`research_manager.py` 解析 JSON（reasoning/rating/confidence），`state["research_manager_conclusion"]` 改为评级前置拼装，另存 `research_manager_rating`/`research_manager_confidence`；解析失败降级为自由文本（不中断，降级可观测）
- [x] 1.8 失败测试 + 实现：RM prompt（research_manager.md）改 JSON 输出模板（键序 reasoning 在前 rating 在后，保持先推理后结论生成顺序）；随 §2.3 一并 deploy_prompts
- [x] 1.9 失败测试：Trader context 与 `research_manager_decision` judge 变量所见文本为评级前置拼装（解析 RM 结论的旧逻辑若存在须移除，单一权威点）
- [x] 1.10 失败测试 + 实现：辩论 context 编号呈现——`_build_debate_context` 各历史发言以「论点: ①…」编号行前置（取 key_arguments）
- [x] 1.11 失败测试 + 实现：`DebateMessage` 新增可选 `rebuttal_to: list[int]`；bull/bear prompt 输出格式加 rebuttal_to 与「回应对方N」标注要求（随 §2.3 一并 deploy_prompts）
- [x] 1.12 失败测试 + 实现：交锋覆盖率计算（各轮 rebuttal_to 并集 / 对方论点总数，纯函数）并进入 debate_quality judge 材料（evals/extract.py 拼装时并列呈现双方论点编号）
- [x] 1.13 失败测试 + 实现（§6.1 健康检查发现）：`call_llm_for_json` 加 `validate` 钩子——JSON 合法但 pydantic 校验不过时带错误摘要重试一次，仍不过向上抛；FM 节点接入（实证：r1 实验 17 条中 1 条 approve 首答缺 action/confidence，未重试直接炸整条 trace，SDK 丢弃 item）
- [x] 1.14 失败测试 + 实现（§6.1 健康检查发现）：`_build_fund_manager_context` 接受 `TradeDecision` 对象——旧 `isinstance(dict)` 守卫遇 risk_judge 原样写入的对象静默跳过，FM 自首次提交起从未看到过审批对象（Langfuse 实证 4/4 trace 的 fund_manager 输入无「交易决策」段；旧测试 fixture 用 dict 喂 state 恰好绕过）
- [x] 1.15 失败测试 + 实现（r1 全量复盘）：分析师解析降级保真——`extract_json` 容忍字符串内未转义成对引号；降级占位改为如实「输出解析失败」并打捞已闭合 summary/plain_conclusion；重跑降级不覆盖既有正常报告（`_keep_valid_over_degraded`）。实证：中芯 fundamental 第 3 代因 `"呈"低盈利"格局"` 解析失败，兜底「数据缺失」覆盖前两代好报告，judge 据此判 decision_grounding 2 分
- [x] 1.16 失败测试 + 实现（r1 全量复盘）：`_rebuttal_coverage` 去重键改为「发言序 + 论点序号」——旧键只用角色+序号，多轮的①被合并，分子封顶单轮论点数，8 条 trace 全报「4/8」
- [x] 1.17 失败测试 + 实现（r1 全量复盘）：降级标记键带 agent 与重试轮次（`degradation.{agent}.r{n}`），分析师节点无独立 span 时不再互相覆盖；节点透传 `state.iteration_count` 为轮次。后续决策：是否给分析师节点建独立 span（改 trace 拓扑）
- [x] 1.18 失败测试 + 实现（r1 复盘）：Risk Judge evidence_refs 来源扩展——`RISK_EVIDENCE_SOURCES` = Trader 来源 + risk_aggressive/risk_conservative/risk_neutral/risk_metrics，别名归一（aggressive→risk_aggressive 等）；risk_judge.md 来源段更新并 deploy_prompts（14 导入）；prompt 漂移守卫按 prompt 分套

## 2. FM 理由职责边界（D2，agent-prompt-contracts）

- [x] 2.1 `prompts/fund_manager.md` 决策语义段追加理由边界条款：限定风控一致性/论据矛盾/执行前提，禁止方向性投资背书（含反例表述）；与 1.3 合并为一次 prompt 变更
- [x] 2.2 失败测试：加载 fund_manager.md 断言边界条款与反例存在（tests/ 对应 prompt 契约测试）
- [x] 2.3 执行 `uv run python scripts/deploy_prompts.py` 发布 prompt（否则 eval 门禁拒绝运行）

## 3. 报告结论层重构（D3，agent-evaluation-suite）

- [x] 3.1 失败测试：report 节点 focus 为空时仍生成聚焦摘要并写 `state["focus_summary"]`（tests/nodes/test_report.py）
- [x] 3.2 实现 `nodes/report.py`：`_build_focus_summary` 无条件调用；focus 空时固定提示词；`generate_report` 返回 `focus_summary` 键
- [x] 3.3 失败测试 + 实现：`evals/extract.py` 的 `report_conclusion` 取值顺序 `state["focus_summary"]` → 回退 `extract_conclusion(final_report)`；补历史 trace 兼容用例
- [x] 3.4 验证 consistency judge 材料中【最终报告结论章节】为聚焦摘要文本、非 FM 复述（用缓存 fixture 或既有 trace fixture 断言）
- [x] 3.5 失败测试 + 实现：deep 报告的 `report` judge 变量改为结构化拼装（研究聚焦 + 各分析师摘要 + RM 结论 + 交易决策要点 + FM 决策，剔除图片 markdown 引用），替代 final_report 全文 head/tail 截断——实证 4f58faf7：4096 截断后 judge 仅见图表路径与审批章，幻觉推断「全面覆盖」恒 5 分
- [x] 3.6 失败测试 + 实现：decision_grounding rubric 模板加【多空辩论记录】{{debate_history}}（rubric v4）+ material DIMENSION_SECTIONS 同步；实证 2fd1ee6d：交易决策 7 条 evidence_refs 有 2 条 debate_bear 来源，judge 输入无辩论记录无法核对（rubric 要求核对未提供的材料，自相矛盾）；实施后 decision_grounding 全量重评
- [x] 3.7 失败测试 + 实现：标注材料人类可读渲染——【交易决策】等节的转义 JSON 解析为人读格式（action/置信度/仓位/论据来源分布/理由分行），解析失败保持原文；展示层渲染不改变信息内容（同口径保持）
- [x] 3.8 report_relevance rubric 口径修订（v3）：「切题=回答了用户的问题」——覆盖维度但回避用户所问的直接决策问题 SHALL ≤3；Safety 约束下如实说明约束并给可行答案 SHALL 视为已回答；失败测试锁定新口径措辞 + decision_grounding 式全量重评报告验证分歧收敛
- [x] 3.9 失败测试 + 实现（r1 复盘）：decision_grounding v6——judge 变量新增 `risk_metrics`（人读一行）与 `risk_debate_history`（按消息截断），rubric 模板加【风控指标】【风险辩论记录】两节 + source 枚举加 risk_*；material DIMENSION_SECTIONS 同步。实证：8 条理由 5 条判风控数字无出处、3 条判中性方论据无出处，2 分置信度 ≤0.5
- [x] 3.10 失败测试 + 实现（r1 复盘）：`_serialize_decision` 在对象内截断 reasoning（2400B），序列化保持合法 JSON——旧路径序列化后被 `_trunc` 挖心致 JSON 残缺，材料人读化失败（茅台 66009ecb）
- [x] 3.11 失败测试 + 实现（r1 复盘）：`evals/run.py` 汇总行 `skipped` 取自 task 输出（旧硬编码 None，3 条有意跳过项显示成「跑了但没分」）
- [x] 3.12 失败测试 + 实现（r2 三道关复盘）：`_rebuttal_coverage` 改为 (role, round) 语义——辩论图按轮扇出并行（route_to_debate_r1/r2 各派两个 Send），rebuttal_to 按 prompt 契约指向对方上一轮；分母只算「对方存在更后轮次」的可回应论点（末轮论点并行结构下永远无人可回应，旧分母把上限压到 50%）；三方/单轮 → None；乱序不变
- [x] 3.13 失败测试 + 实现（r2 三道关复盘）：`risk_judgment` 变量裁决 JSON 保持完整、风险辩论尾部只在剩余预算内追加（旧整体 _trunc 挖掉闭合括号，consistency 材料【Risk Judge 裁决】9/9 残缺）
- [x] 3.14 失败测试 + 实现（r2 三道关复盘）：材料人读化逐条列出 evidence_refs「[source] claim」——旧版压成来源分布，标注人看不到任何 claim 而 judge 所见 JSON 每条都在，decision_grounding 人/judge 材料不等价

## 4. 用户意图贯穿（D4/D5，user-intent-propagation）

- [x] 4.1 失败测试：query 命中标签时入口合成弱 focus（「分析…适不适合作为长期持有股买入」→ mid_long_term 等）；零命中 focus 保持空；query 全文不进分析师 context
- [x] 4.2 实现 `api.py` 深度分析入口的兜底提取（复用 parse_focus_tags 词表）
- [x] 4.3 失败测试 + 实现：`_build_debate_context` 与 `_build_risk_context` 注入 `focus_hint(state)`；focus 空时零注入回归用例

## 5. 集成验证

- [x] 5.1 `uv run pytest` 全绿 + `uv run ruff check` + `uv run mypy` 通过——门禁口径（-m "not live"）2182 passed；顺手修复 tests/outcome/test_trace_capture.py 3 条 approve mock 未随 D1 契约补 action/confidence 的既有失败
- [x] 5.2 本地跑 1 条深度分析（真实 LLM）：确认 FM 输出含 action/confidence、报告含研究聚焦与并排定性、辩论/风控 context 含关注点行（Langfuse trace 人工核对）——7/7 通过
- [x] 5.3 若涉及前端 FM 展示：E2E 门禁通过（交互类变更红线）；无前端改动则本项标注「不适用」——不适用（本 delta 无前端改动）

## 6. 评估收口（实施后）

- [x] 6.1 重跑 dataset 实验（baseline 池）：`baseline-decision-semantics-r1` 16/17 完成，37/37 judge 分落库、confidence 100% 落库（0.40–0.95）、judge_failures=0；1 条（`deep 分析平安`）因 FM 缺字段崩溃 → 1.13/1.14 修复。契约抽验全绿：无图片路径 13/13、论点编号+覆盖率+【bear】8/8、decision_grounding 四节 8/8、consistency 五节+RM 评级前置 8/8、【最终报告结论章节】已为聚焦摘要
- [x] 6.1b 以修复版重跑 r2（00:16Z）与 r3（02:08Z，含预算放宽/覆盖率并行语义/JSON 完整/evidence 逐条）；r3 三道关 41/41 通过，复盘见 docs/evals/2026-09-11-judge校准复盘-round5到r3问题发现链.md：r1 的 FM 决策全部在看不到方案的前提下做出，consistency 维度的 judge 分与 round6 人工标注反映的是「盲审批」行为，非修复后行为
- [ ] 6.2 consistency 与 decision_grounding 维度重评（FM 序列化 + report_conclusion 变更影响面）；report_relevance/debate_quality 无需重评（judge 变量未变）
- [ ] 6.3 对照 round5 基线归档对比报告（tests/validation/ 或 docs/evals/），rubric v2「评分前必读」段的简化评估（可简化则 rubric 升 v3 走独立校准）
- [ ] 6.4 round7 盲标：`evals/judge_calibration/data/judge-sample-round7-blind.xlsx`（41 行/14 trace，锁定 r3；round6/r1 表因 FM 盲审批作废）人工回填后 measure → 与 round5 对比；report_relevance/debate_quality judge 零方差，以 MAE/方向一致率为主
