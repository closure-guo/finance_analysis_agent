## Context

### 现状

Layer V Fund Manager 是全系统唯一「LLM 直供 → 无校验 → 驱动路由 → 兜底放行」的完整链路：

- `nodes/fund_manager.py:19` 用 `data["decision"]` 裸取键，无枚举白名单、无默认值、无异常处理
- `routing.py:23-28` 的 `after_fund_manager` 只显式判断 `"return"`，其余全部落入 `return "generate_report"`
- `routing.py:25` 的 `.get("fund_manager_decision", "approve")` 把「决策缺失」等同于「批准」

两者叠加后，LLM 输出 `"REJECT"` / `"拒绝"` / `"revise"` 与输出 `"approve"` 走完全相同的分支，且无任何日志或告警。

对比 Layer III Trader（`nodes/trader.py:18`）用 `TradeDecision.model_validate(data)`，其 `action` 受 `models.py:50` 的 `Literal["buy","sell","hold","watch"]` 约束——项目内已有既定的强校验风格，Layer V 未遵循。

### 约束

- **TESTING stub 掩盖问题**：`_llm_utils.py:89-93` 的 fund_manager stub 恒返回 `{"decision": "approve"}`，所有 stub 管线测试对枚举漂移不敏感。新增校验的有效性只能靠直接针对节点的单元测试保证
- **Prompt 双源**：`prompts/loader.py:38-50` 是 Langfuse production label 优先、本地 `*.md` 仅兜底（ADR-0016）。改本地 prompt 不必然改变线上实际下发内容
- **引用校验链路脆弱**：`docs/incidents/006-citation-infinite-loop-20260716.md` 记录过 `citation_pass=False` 触发无限 retry 的事故。根因之一是「LLM 产出的 `field_ref` 与 state schema 路径常不匹配 → 至少一条 FAIL → 持续 retry」。该链路对「让校验失败」这类改动高度敏感
- **异常统一兜底**：节点抛出的异常由 `agent_factory.py:558` 的 `except Exception` 捕获，会话置 `failed`，前端展示错误。故「抛错中断」不会导致连接悬挂

## Goals / Non-Goals

**Goals:**

- Fund Manager 决策值受 `Literal` 强约束，非法值显式失败而非静默降级为 approve
- 容许大小写与首尾空白差异，避免因 LLM 输出格式抖动造成无意义的管线失败
- `reject` 决策在报告中有明确的「未通过审批」语义标注，兑现 ADR-0011:67 的设计意图
- 分析师解析降级从完全静默变为可观测（WARNING 日志 + 下游可识别标记）
- `DebateMessage.role`、`TradeDecision.confidence` 补齐运行期约束
- 补齐 5 个 LLM 解析节点的异常路径测试（当前为零）

**Non-Goals:**

- 不改变 `reject` 的路由走向。ADR-0011:67 规定 Reject → 报告生成（标注未通过审批），当前 `routing.py` 让 reject 与 approve 同走 `generate_report` 符合该设计。`tests/test_routing.py:39-41` 已将此固化为基线，本次不动
- 不引入同义词映射表（如 `revise` → `return`）。同义词归一化有误判风险且需长期维护，非法值应显式失败并通过 prompt 加固从源头减少
- 不改造 `analysts.py` 降级路径的**存在性**。该降级保障了单个分析师解析失败不拖垮整条管线，是有意设计，本次只让它可观测
- 不改 `citation_pass` 的判定逻辑（`failed == 0`），不新增 retry 触发条件（见下方决策 4）
- 不涉及数据库迁移、API 契约、前端改动

## Decisions

### 决策 1：Fund Manager 用 Pydantic 模型校验，与 Trader 对齐

新增 `FundManagerDecision` 模型，`decision` 字段用 `Literal["approve", "reject", "return"]`；节点改为 `FundManagerDecision.model_validate(data)` 后取值。

**为何不用手写 if 白名单**：Pydantic 与 `nodes/trader.py:18` 的既有做法一致，异常信息结构化（字段名 + 期望值 + 实际值），且缺键与非法值统一为 `ValidationError`，无需分别处理 `KeyError`。手写校验会产生两套异常风格。

**为何不降级为 reject**（用户已确认选择抛错）：降级需要判断「LLM 到底想表达什么」，而这正是不可靠的部分。金融场景下「猜错方向」比「显式失败」代价更高。抛错后会话置 `failed`，用户可重试，语义清晰。

### 决策 2：归一化在校验之前，且只做大小写与空白

在 `model_validate` 前对 `decision` 做 `str(value).strip().lower()`，再交给 `Literal` 校验。

**为何容许大小写**：LLM 输出大小写不稳定是普遍现象（`"Approve"` / `"APPROVE"`），这类差异不引入语义歧义，拦截它只会制造无意义的失败。

**为何不容许同义词**：`"revise"` 到 `"return"` 的映射是人的推断，不是 LLM 的表达。一旦开始维护同义词表，边界会不断扩张（`"批准"`？`"OK"`？`"yes"`？），且每次误判都是静默的错误决策。

**实现位置**：用 Pydantic 的 `field_validator(mode="before")` 做归一化，使归一化与校验封装在模型内，节点侧无需关心。

### 决策 3：state.py 用 Literal，与 analysis_type 对齐

`fund_manager_decision` 从 `str  # approve | reject | return` 改为 `Literal["approve", "reject", "return"]`。

TypedDict 的 `Literal` 只提供静态检查（运行期不校验），真正的运行期保障来自决策 1 的 Pydantic 模型。两者互补：mypy 捕获代码中的错误字面量赋值，Pydantic 捕获 LLM 的错误输出。`state.py:19` 的 `analysis_type` 已是此风格。

### 决策 4：降级标记不通过 citation_pass 表达（关键决策）

分析师降级报告携带独立的降级标记字段，**不**让 `citation_pass` 变为 `False`。

**为何**：`docs/incidents/006` 的事故根因之一是 `citation_pass=False` 触发持续 retry，而每次 retry 都是一轮完整的分析师 LLM 调用（实测单轮 100s+）。如果让「解析失败」也触发 retry：

- 解析失败往往源于 LLM 输出格式问题，重试同一 prompt 未必能修复，可能连续 3 次全败
- 代价是 3 轮昂贵的 LLM 调用 + 数百秒延迟，换来的可能仍是降级报告
- 与「降级存在的初衷」矛盾——降级正是为了让管线在单点失败时仍能产出结果

**替代方案**：降级标记用于**可观测性**而非**控制流**。WARNING 日志 + Langfuse span metadata 使问题可被发现和统计，但不改变图的走向。若后续数据表明降级率过高，再单独决策是否引入重试策略。

**取舍**：这意味着「解析失败导致的零 claim」仍会使 `all_passed=True`。这是有意接受的——用可观测性换取管线稳定性，而非用重试换取正确性。

### 决策 5：Report 标注用映射表而非 if 链

`report.py:290-292` 改为按决策值查中文标注映射（approve → 审批通过 / reject → 未通过审批 / return → 已退回交易员重新评估）。

因 `decision` 已受 `Literal` 约束，映射表必然命中，无需兜底分支。这与 `api.py:347-353` 的三段 if + 兜底文案不同——那里的兜底是为应对当前无约束的现状，本次加固后可简化，但 `api.py` 的简化属可选项，不作为必须项（见 tasks 中的可选任务）。

### 决策 6：role 与 confidence 的约束范围

- `DebateMessage.role` 改 `Literal`，涵盖 7 个值：`bull`、`bear`、`aggressive`、`conservative`、`neutral`、`research_manager`、`risk_judge`（取自 `models.py:37` 现有注释）
- `TradeDecision.confidence` 补 `Field(ge=0, le=1)`
- `DebateMessage.round` 补 `Field(ge=1)`

**风险提示**：`role` 改 `Literal` 后，若某个辩论 prompt 引导 LLM 输出了不在 7 值内的角色，会从「静默透传」变为「管线失败」。需在实施时核对全部辩论相关 prompt（`prompts/risk_debater.md`、`prompts/bull_researcher.md`、`prompts/bear_researcher.md` 等）声明的 role 取值，确保与 `Literal` 集合一致——这与本次 spec 的 Prompt Enum Consistency 要求同源。

## Risks / Trade-offs

**[Fund Manager 抛错使原本能出报告的分析彻底失败] → 缓解**：这是有意的行为变更（proposal 已标 BREAKING）。抛错发生在 Layer V，此时前四层的分析结果已在 state 中，且异常经 `agent_factory.py:558` 捕获后会话置 `failed` 并带错误信息，用户可见可重试。相比「静默按批准出报告」，显式失败是更小的代价。实施时需确认 Langfuse trace 能记录该失败（`open_span` 的异常状态记录见 issue #28，属独立问题）。

**[role 改 Literal 导致既有 prompt 触发失败] → 缓解**：实施时先核对全部辩论 prompt 的 role 声明，并同步核对 Langfuse production 版本（`prompts/loader.py:38-50`）。若发现 prompt 声明的值与 `Literal` 集合不符，优先改 prompt 而非放宽 `Literal`。此项列为实施前置检查任务。

**[sentiment_analyst prompt 的 textual 修正后，Langfuse 上仍是旧版] → 缓解**：本地 md 与 Langfuse 版本需同步。任务中显式包含「核对 Langfuse production 版本」步骤，且该修正本身是安全的——即使 Langfuse 未同步，现状（静默改写为 `entity`）也不会恶化，只是修正未生效。

**[confidence 补 ge/le 后，历史 LLM 习惯返回百分数导致频繁失败] → 缓解**：先核对 `prompts/trader.md` 与 `prompts/risk_judge.md` 中 confidence 的示例值与说明措辞，确保 prompt 明确要求 0-1 小数。若 prompt 措辞模糊需一并加固。

**[降级标记不触发 retry，解析失败仍会产出低质量报告] → 有意接受**：见决策 4。取舍是「管线稳定性 + 可观测性」优于「用昂贵重试换取不确定的改善」。后续可依据 Langfuse 上的降级率数据再评估。

**[本次改动面较大（3 个缺陷 + 报告呈现），单次 PR 风险集中] → 缓解**：tasks 按缺陷维度分组，每组独立可验证（各自有单元测试），组间无强依赖。可按组分批提交，每组提交前跑全量后端测试。

## Migration Plan

无数据迁移。部署为纯代码变更。

**回滚策略**：本次改动全部集中在校验强度与日志，无状态结构变更、无 DB schema 变更。回滚只需 revert 提交，历史会话数据不受影响（`fund_manager_decision` 在 DB 中存的仍是字符串，`Literal` 仅约束新写入）。

**注意历史数据**：DB 中可能存在旧会话的 `fund_manager_decision` 为非法值（本次修复前写入的）。`state.py` 的 `Literal` 是静态标注不影响读取，`report.py` 的映射表需确认对历史非法值的容错——若映射未命中应回退显示原始值而非抛错（读路径不应因历史数据失败）。此项在 tasks 中列为显式验证点。

## Open Questions

- `api.py:347-353` 的三段 if + 兜底文案在加固后可简化为映射表，但兜底对历史数据仍有价值。倾向保留兜底、不做简化，列为可选任务
- Fund Manager 抛错时是否需要向 Langfuse 上报专门的 score（类似 `citation_pass` 的做法）以便统计枚举违约率？倾向本次不做，先靠 WARNING 日志观察，避免范围继续扩张
