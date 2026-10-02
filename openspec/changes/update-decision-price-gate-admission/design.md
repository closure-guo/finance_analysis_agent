# Design: update-decision-price-gate-admission

## Approach

risk_judge 门禁回路的判定尾部改为恶化判据分层（其余链路零改动）：

1. 首次 `_run_price_check` 后保存 `first_sources = {a["source_text"] for a in anomalies if isinstance(a, dict)}` 与 `first_count`；
2. 打回重试 + 复检后残留非空时：
   - `resid_sources` 同法提取；`worse = len(resid) > first_count or any(s not in first_sources for s in resid_sources)`；
   - `worse` → 既有 fail 路径（note「已打回仍未通过且恶化：N 条残留」措辞精确化为含恶化语义）；
   - not worse → `decision_price_gate = {"result": "pass", "note": f"打回后残留 {len(resid)} 条未清零（未恶化，放行待人工终裁）"}`，残留照落 `decision_price_anomalies`；
3. source_text 作为同源判据的理由：它是校验器提取的原文片段（`_excerpt`），LLM 改写文本必然产生新片段 → 「残留片段 ⊆ 首次片段」精确刻画「LLM 未采纳修正且未引入新错误」；模糊匹配不需要（改写即新文本，按恶化处理是保守正确的方向——宁阻断不误放）。
4. FM/report/API 零改动：gate result 仍只有 pass/fail 两值，路由与归因读 result 不读 note；放行形态的 note 经 FINAL_CHECK_LABELS 自动进 FM 上下文；报告侧 gate note 不含「仍未申报/缺失」markers，不泄入「结构不完整」块（T4 回归锁已覆盖该不变量）。

## Alternatives Considered

- **方案 A：残留即阻断（现状）**——不选：incident 034 实证 LLM 合理申辩被句法盲区误杀，用户拿不到报告的代价大于误放风险（残留有 trace 观测兜底）。
- **方案 B：语义相似度判定「同源」**——不选：引入模糊匹配的不确定性；source_text 精确集合运算确定性可测，且保守方向正确（模糊地带按恶化阻断）。
- **方案 C：放行形态报告渲染警示行**——不选：报警退出交付物的原则不变（PR #192 语义）；观测走 trace + FM 上下文。

## Risks

- **误放真顽固错误**：LLM 重试原样输出同一幻觉价位的 stub 场景（故障注入测试形态）——该形态 source_text 不变、条数不增，按新规则会放行。裁决：这正是「未恶化放行+待终裁」的设计意图（stub 的同源残留本就无法区分于合理申辩，交给 trace 人工终裁）；真幻觉的兜底是下一跑次的数据变化 + 终裁通道。既有故障注入测试断言需按新分层更新（同源残留 → 放行断言；恶化残留 → 阻断断言）。
- **恶化判据的边界**：首次 2 条残留 1 条（减少但剩余条目同源）→ 未恶化放行——正确（LLM 有改善，剩余为申辩）；首次 1 条残留 1 条但文本微调 → 新 source → 阻断——保守正确。
