# Design: add-output-contract-guard

## Approach

**分层职责**（不改动网关请求路径）：`llm-output-resume`（017/019 治理）守**完整性**——finish_reason=length 时续写；本合同守**正确性**——内容本身违约（泄露独白、句中截断直通、raw_reasoning 当正文）不得进交付物。两层独立，互不替代：就算续写成功，交付的仍可能是泄露独白的加长版，必须由内容级校验把关。

**校验器**：新增 `src/finance_agent/llm/output_guard.py` 纯函数 `validate_deliverable_text(text, *, target_lang="zh", finish_reason=None) -> GuardVerdict`，三类规则：

1. **泄露模式**：任务独白标记（`The user wants`、`Draft:`、`Let me ` 等行首/句首模式），规则集以 incident 036 实测泄露样本为基准、以中远海能 14:49 干净样本为反例双向校准
2. **语言占比**：中文交付物要求中文字符占比 ≥ 阈值（初值 0.6，按回归集调准）
3. **截断信号**：`finish_reason=length` 直接判截断；finish_reason 不可得时（incident 036 观测缺口）用正文末尾启发式（悬空数字/逗号/连接词收尾）

**接入点**：`_build_focus_summary`（`src/finance_agent/nodes/report.py`）在 `complete_text` 返回后、嵌入前调用。违约处置两级：定向重试 1 次（强化指令「直接输出最终文本，禁止解释思考过程」，复用原 materials）→ 仍违约走该函数既有的结构化拼接兜底（materials[0] 截断，该兜底已存在）。同时删除 report.py:340 的 `or meta.get("raw_reasoning")` 回退。

**遥测**：`complete_text`（`src/finance_agent/llm/gateway.py`）metadata 补 `finish_reason` / `resume_count`；guard 判定结果与命中规则经 `trace={"metadata": ...}` 进 Langfuse。

## Alternatives Considered

- **方案 A：prompt 强化**（「只输出摘要不要思考过程」）——不选。对模型行为无硬约束，017/019 已证 prompt/预算层不可靠，glm-5.3 间歇性（2/3 泄露率）恰是 prompt 层防不住的形态
- **方案 B：网关层对所有 complete_text 统一拦截**——不选。多数调用是结构化 JSON（已有 extract_json 合同）或进 state 的中间产物，不直接进交付物；网关层不知道「交付物」语义，判定放调用侧最准，且避免给非交付路径加误伤面
- **方案 C：LLM 自审**（再调一次模型判泄露）——不选。违背「确定性校验不依赖模型自觉」原则（incident 036 核心教训），且引入额外延迟与成本

## Risks

- **误伤干净输出**（中远海能 14:49 反例）→ 双向校准 + 直通单测锁定；guard 仅在交付物路径启用，不影响其他调用；误伤判定在 spec 中明确定义为校验器缺陷
- **规则被新泄露形态绕过**（新模型新花样）→ 判定结果进 trace 可观测，命中率进 metrics；换模型回归集（拓荆五版历史输入）全量重跑（incident 036 处置 3 的流程纪律）
- **重试延迟翻倍** → 仅违约时重试；按 2/3 泄露率估算 quick 调用平均延迟约 +33%，purpose=quick 300s 超时充裕
