# Design: add-decision-hysteresis

## Approach

（proposal 级设计草案——实施前经 writing-plans 细化）

两层约束，挂点均在 risk_judge（决策语义出口，且已有打回回路基建）：

1. **均衡带判定（确定性计算，不新增 LLM 调用）**：输入 = `research_manager_rating`（中性即均衡必要条件）+ 辩论锚点统计（`debate_anchor_checks`/bull-bear 论点数与锚定率，势差阈值待校准）。产出 state 键 `decision_hysteresis.balanced_zone: bool`。均衡带 + 执行动作 + reasoning 无增量关键词（披露/公告/跌破/放量收复等事件词表，代码判定）→ 打回重申一次（反馈列明增量类型清单）→ 仍无 → 输出降级 watch + 标注。
2. **方向滞回（读历史，不改历史）**：`predictions` 库新增只读查询 `recent_decisions(symbol, window_days=5)`（含方向/日期/置信度）；序列注入 risk_judge context（「近窗决策史」节）；输出方向 ≠ 前向方向且 reasoning 无增量申报 → 打回重申一次 → 仍无 → `model_copy` 改 action 为前向方向 + 标注「维持前判（无证据增量）」+ inaction_reason 补写滞回理由（复用 require-watch-hold-rationale 契约，非执行动作必有理由）。

**打回预算合并**：均衡带与滞回共用一次重申（两条件同时触发时反馈合并，避免打回叠加烧配额）——与价位门禁打回的关系：价位门禁在其后独立执行（不同反馈域）。

## Alternatives Considered

- **多数投票（同输入跑 k 次取众数）**——不选：k 倍 LLM 成本（pass@k 实验单跑 ~10 分钟）；滞回零边际成本。
- **温度调零/seed 固定**——不选：不解决证据均衡的本质（同一证据下两方向都「对」），只是把掷硬币变成固定的掷硬币；且供应商兼容面差。
- **滞回放 Research Manager 层**——不选：RM 是评级层不是执行层；方向翻转的申报义务在执行决策出口。

## Risks

- **增量事实关键词表误判**（把非增量表述当增量）→ 首版从严（窄词表），漏放优于误拦；词表进 prompt 契约（agent-prompt-contracts）+ 校准走 evals。
- **predictions 库数据质量**（incident 032 重建待办）→ 查询带 `status` 过滤 + 空结果即不生效（fail-open）；重建后自然收紧。
- **滞回锁死正确翻转**（真增量被词表漏判）→ 打回重申给了 LLM 二次申报机会；重申反馈列明增量类型清单降低漏报；极端场景人工终裁通道兜底。
- **watch/hold 前向 + sell 现货场景**（用户明确要卖）→ 滞回约束的是「管线自主决策」，用户显式指令路径（follow-up 追问）不在本 delta 范围。

## Open Questions（writing-plans 前需裁决）

1. 辩论势差的量化阈值（锚点统计的哪个分布指标、切点多少）——建议首版仅用 RM 中性评级做均衡带判据（简单确定性），辩论势差二期加。
2. 降级 watch 的置信度继承（沿用重申输出的置信度 vs 固定低置信）。
3. prompt 契约变更集（risk_judge 增量申报段 + RM 评级格式）与 deploy_prompts 排期。
