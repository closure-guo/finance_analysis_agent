## Context

决策层「全 watch」取证（`docs/evals/2026-09-21-决策层全watch取证.md`）确认非执行动作（watch/hold）占生产流量 89%，成因是 Trader 默认姿态；报告渲染对这类决策只有占位行「再评估触发条件: 见理由」，`report-decision-rendering` spec 明确记录「当前决策 JSON 无结构化触发字段，不得凭空编造」。owner 选定取证选项 b。既有可复用先例两套：① 价位必填化（`require-trade-price-declaration` / `extend-payout-self-check-coverage`）——schema 保持宽松、规则节点承担必填约束、打回一次仍缺失放行+如实标注；② 字段噪声归一（`evidence_refs` / `anchors` 清洗）。B5 可执行性 rubric（`evals/causal_ablation/family_b_judge.py:227`）已在按「明确的再评估触发条件」评分，judge 材料经 `_serialize_decision` 序列化决策对象，新字段自动进材料。

## Goals / Non-Goals

**Goals:**

- watch/hold 决策结构化申报「不行动原因 + 再评估触发条件」，经管线保证产出（两侧打回回路）
- 报告结构化渲染两者；缺失时诚实标注「未申报」，不编造
- 下游 judge（B5 可执行性 / consistency）自动获得可评字段

**Non-Goals:**

- 不改变动作分布（watch 主导是取证结论下的既有事实，本变更只提升非执行动作的信息含量）
- 不改交易员 prompt 的置信度锚定（那是取证选项 a，未选）
- 不改价检语义、不改图结构（节点名与边不变）
- 不做触发条件的自动跟踪/回溯结算（未来增量，见 Open Questions）

## Decisions

### D1 字段形态：`inaction_reason: str | None` + `reeval_triggers: list[str]`

- 与 `reasoning` 的分工：`reasoning` 是整体决策叙述；`inaction_reason` 是「当前不满足执行条件的点」（如「估值分位高且缺催化剂」「关键财务数据待季报验证」）；`reeval_triggers` 是可观察条件条目（如「价格回落至 X 区间」「季报毛利率低于 Y」）。
- 备选：只用 `reeval_triggers`（理由继续藏在自由文本）——否决：取证选项 b 明确要求两者，且「为何不行动」是可判分的一等对象（B5 rubric 区分「观望等待好转」与具体理由）。
- 命名：`inaction_reason` 对 watch/hold 同构（不叫 `watch_reason` 以免 hold 误读）。
- 清洗：`reeval_triggers` 沿用 `anchors` 先例（str → 单元素列表；None/非列表 → []；非 str 条目丢弃）；`inaction_reason` 纯空白視同缺失。清洗只归一形态，不抛异常。

### D2 约束落点：规则节点而非 schema 硬校验

- trader 侧：`validate_trade_prices` 节点内新增非执行动作理由检查（与价位检查同一节点、独立键与独立 attempts 计数）。节点名保留（改名会波及图通道、前端管线时间线、E2E 断言，收益为负）。
- 终稿侧：`risk_judge` 内终稿检查（同 `final_price_check` 回路）扩展理由完整性——终稿是报告渲染与落库的对象，必须在终稿侧兜底。
- 备选：schema 层 `model_validator` 硬拒（action==watch 缺字段抛 ValidationError）——否决：LLM 抖动会中断整条管线（`anchors` 曾因 str 形态炸 full-graph 的教训），且与价位必填化的「宽松 schema + 规则打回」先例不一致。

### D3 回路语义：打回一次 → 仍缺放行 + 如实标注

- trader 侧 fail → feedback（列出缺失项）经 `inaction_rationale_feedback` 注入 trader context（同 `price_check_feedback` 通道）；仍缺 → pass + note「已打回仍未申报」。
- 终稿侧同款一次重试；仍缺 → 放行 + 标注。
- 理由：与价检语义对齐、避免死循环；缺失是「信息量退化」而非「正确性破坏」，放行+标注让缺口在报告与 judge 材料里可见（同「未提供」价位先例）。

### D4 state 键

新增 `inaction_rationale_check: dict`（{result, note}）、`inaction_rationale_attempts: int`、`inaction_rationale_feedback: str`。声明入 `AnalysisState`，过「节点产出键 ⊆ AnalysisState 声明与图通道」门禁。

### D5 报告渲染

watch/hold 分支：`- **不行动原因**: <值>`；`- **再评估触发条件**: ① … ② …`（非空列表时）；缺失渲染 `未申报`。替换现有 `- **再评估触发条件**: 见理由` 占位。`report-decision-rendering` 对应 scenario MODIFIED。

### D6 prompt 契约与发布

`trader.md`：输出要求段 + JSON 示例补 watch/hold 形态；`risk_judge.md`：继承要求（可改写内容，不得置空）。按 `prompt-deploy-consistency` 纪律执行 `uv run python scripts/deploy_prompts.py` 发布，否则 eval 门禁拒绝运行。stub 契约：`_STUB_TRADE_DECISION`（hold 形态）补字段，`test_stub_contract_sync` 护栏强制同步。

## Risks / Trade-offs

- [prompt 加字段后 watch/hold 输出变长，token 成本小增] → 字段短约束（`inaction_reason` 一句话、触发条件 ≤3 条）写进 prompt；成本可观测（eval 侧 latency/cost 指标已在）
- [LLM 把 triggers 写成空泛短语（「等待好转」）] → prompt 明确「可观察、可判定」要求；B5 rubric 已惩罚空泛表述；真实链路验证时抽查条目质量
- [看板/judge 口径变化：新字段进 materials 后 B5 打分基线可能移动] → 属预期增益（rubric 本就在评该项）；消融/校准对比按「同噪声下的相对差异」解读，不追历史绝对分
- [重复字段语义（`inaction_reason` vs `reasoning` 重叠）] → prompt 中钉死分工（整体叙述 vs 不行动依据）；真实链路抽查，若普遍重复再收敛字段
- [打回回路增加一次 LLM 调用] → 仅在缺失时触发，且两侧各至多一次；与价检回路同源，成本形态已知

## Migration Plan

1. 模型 + 清洗 + 测试（红→绿）
2. 两侧回路 + 反馈注入 + 测试
3. 报告渲染 + 测试（替换既有 `见理由` 断言）
4. prompt 契约 + `deploy_prompts` 发布 + stub 契约同步
5. 真实链路验证（依赖 docker/Langfuse 可用；验证报告落 `tests/validation/`）
6. 回滚：纯增量字段与渲染分支，回滚即 revert 提交；历史决策对象渲染兼容（未申报标注）

## Open Questions

- 触发条件的后续消费：是否纳入 outcome 结算/再评估提醒（decision-outcome 侧），留待本变更落地后按使用数据决定
- `reeval_triggers` 条数上限（prompt 建议 ≤3）是否需要在规则侧硬约束——先 prompt 软约束，观察真实分布再定
