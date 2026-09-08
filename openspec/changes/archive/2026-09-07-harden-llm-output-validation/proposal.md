## Why

Layer V Fund Manager 的决策值由 LLM 直接产出且**无任何枚举校验**（`nodes/fund_manager.py:19` 裸取 `data["decision"]`），而 `routing.py:23-28` 的 else 分支把任何非 `return` 的值都放行到 `generate_report`。两者叠加形成完整的静默失败链路：LLM 输出 `"REJECT"`（大小写）、`"拒绝"`（中文）、`"revise"`（同义词）时，系统**静默当作批准处理**，全链路零告警。在金融决策场景中，「基金经理拒绝方案」被悄悄执行成「批准」具有实质风险。

排查中另发现两处同类缺陷：`nodes/analysts.py:45-56` 的 catch-all 降级会把解析失败伪装成「空 claims 报告」，进而使引用校验假性通过（`citation.py:66` 的 `all_passed=failed == 0` 在零 claim 时返回 True），绕过 retry 分支直接出报告；`models.py` 中 `DebateMessage.role`、`confidence`、`round` 的取值约束只存在于注释里，LLM 串角色或返回越界置信度不会被发现。

这些行为在 `openspec/specs/` 下**均无规格定义**（7 个现有 spec 无一覆盖 Agent 节点的 LLM 输出契约），处于「行为未定义」状态，故需 delta 先行确立契约再实施加固。

## What Changes

### 1. Fund Manager 决策枚举强校验

- `models.py` 新增 `FundManagerDecision` Pydantic 模型，`decision` 字段用 `Literal["approve", "reject", "return"]` 约束，与既有 `TradeDecision.action`（`models.py:50`）的做法对齐
- 校验前对 LLM 输出做归一化：`strip()` + `lower()`，容许 `"Approve"` / `" approve "` 这类大小写与空白差异（LLM 输出大小写不稳定是常见现象，此类容错不引入语义歧义）
- 归一化后仍非法则抛 `ValidationError` 中断管线，**不做语义降级**——与 `nodes/trader.py:18` 的 `TradeDecision.model_validate` 行为一致
- `state.py:97` 的 `fund_manager_decision` 从宽松 `str` 改为 `Literal["approve", "reject", "return"]`，与同文件 `analysis_type`（第 19 行）的既有风格对齐

### 2. Reject 报告标注补齐

- ADR-0011:67 规定 Reject 应「报告标注"未通过审批"」，但 `nodes/report.py:290-292` 仅把原始字符串插入 Markdown（渲染为 `**reject**`），缺少该语义标注
- 补齐三种决策的中文标注呈现，使报告读者能明确区分「已批准」与「未通过审批」

### 3. Analyst 解析降级显式化

- `nodes/analysts.py:45-56` 的 `except Exception` catch-all 收窄，并在降级时记录 WARNING 日志（当前完全静默）
- 降级产出的报告需携带可识别标记，使下游能区分「LLM 确实无 claims」与「解析失败导致 claims 为空」，避免 `citation_pass` 假性通过
- `_sanitize_claims`（`analysts.py:33-36`）对非法 `claim_type` / `source_type` 的强制改写补记 WARNING，当前静默改写为 `entity` / `data`
- 修正 `prompts/sentiment_analyst.md:42` 与 `analysts.py:19-26` 白名单的不一致（prompt 要求 `textual`，但该值不在合法集内，导致舆情 claims 被系统性改写）

### 4. DebateMessage / TradeDecision 字段约束补齐

- `models.py:37` `DebateMessage.role` 改用 `Literal`，覆盖 7 个合法角色值
- `models.py:52` `TradeDecision.confidence` 补 `ge=0, le=1` 约束（docstring 第 48 行已声称 0-1，但无运行期约束，LLM 返回 `95` 会渲染成「置信度 9500%」）
- `models.py:38` `DebateMessage.round` 补范围约束

### 5. 异常路径测试补齐

当前 `tests/nodes/` 下 5 个 LLM 解析节点的异常路径测试为零。补齐：

- Fund Manager：`reject` 用例、非法枚举值用例、缺 `decision` 键用例、大小写归一化用例
- Analyst：坏 JSON 触发降级路径用例、`_sanitize_claims` 两个纠偏分支用例
- `tests/test_routing.py:39-41` 的 `test_reject_returns_generate_report` 需补充说明性注释——该用例把「reject 走 generate_report」固化为基线，符合 ADR-0011:67 的「→ 报告生成」语义，但需明确它不代表「reject 等价于 approve」

**BREAKING**：LLM 输出非法决策值时行为从「静默降级为 approve」变为「抛 ValidationError 中断管线」。这是有意的行为变更——静默放行在金融场景不可接受。管线失败会被 `agent_factory.py:558` 捕获并置会话为 `failed`，前端展示错误信息。

## Capabilities

### New Capabilities

- `agent-node-contracts`: Agent 节点对 LLM 输出的解析与校验契约。定义各节点枚举字段的合法取值、归一化规则、非法值处理策略（抛错中断 vs 降级告警）、以及降级路径的可观测性要求。覆盖 Layer I 分析师、Layer II/IV 辩论、Layer III/IV 交易决策、Layer V 基金经理审批。

### Modified Capabilities

无。现有 7 个 spec（e2e-core-specs / e2e-infrastructure / frontend / pipeline-events / session-persistence / session-streaming / trace-observability）均不涉及 Agent 节点的 LLM 输出契约，本次为全新契约域。

## Impact

**源码**

- `src/finance_agent/models.py` — 新增 `FundManagerDecision`；`DebateMessage.role` / `round`、`TradeDecision.confidence` 补约束
- `src/finance_agent/nodes/fund_manager.py:18-19` — 裸取键改为模型校验 + 归一化
- `src/finance_agent/nodes/analysts.py:33-36, 45-56` — 降级与改写补 WARNING 日志、降级标记
- `src/finance_agent/nodes/report.py:290-292` — reject 报告标注
- `src/finance_agent/state.py:97` — `fund_manager_decision` 改 `Literal`
- `src/finance_agent/prompts/sentiment_analyst.md:42` — 修正 `textual` 不一致

**测试**

- `tests/nodes/test_fund_manager.py` — 补 reject / 非法值 / 缺键 / 归一化用例
- `tests/nodes/test_analysts.py` — 补降级路径与纠偏分支用例
- `tests/nodes/test_debate.py`、`tests/nodes/test_risk.py` — 补非法 role 用例
- `tests/test_routing.py:39-41` — 补说明性注释
- `tests/test_models.py` — 补新模型与新约束用例

**风险与注意事项**

- `prompts/loader.py:38-50` 是 Langfuse production label 优先、本地 md 仅兜底（ADR-0016）。修改 `sentiment_analyst.md` 需同步核对 Langfuse 上的 production 版本，否则线上实际下发的 prompt 不变
- `_llm_utils.py:89-93` 的 TESTING stub 恒返回 `approve`，所有 stub 测试对枚举漂移不敏感；新增校验的有效性需靠单元测试直接覆盖，不能依赖 stub 管线测试
- `analysts.py` 降级路径的现有行为被 `citation.py:66` 间接依赖（零 claim 时 `all_passed=True`），收窄降级需同步验证 `after_citation`（`routing.py:31-37`）的 retry 分支不被意外触发，注意 `docs/incidents/006-citation-infinite-loop-20260716.md` 记录过引用校验死循环事故
- 无数据库迁移、无 API 契约变更、无前端改动
