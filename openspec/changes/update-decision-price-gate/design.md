# Design: update-decision-price-gate

## Approach

**门禁挂点：risk_judge 内第 4 个打回回路 + 出口条件路由。**

校验对象是 risk_judge 终稿（payout self-check 之后的 reasoning/reeval_triggers/inaction_reason 文本），且该节点已有一个成熟的三连打回模式（final_price_check / final_inaction_check / final_reeval_check：缺失 → 携反馈直调 LLM 重出完整决策 JSON → 复检；仍缺 → 如实标注）。价位交叉校验门禁复用同构回路，最小改动、风格一致：

1. `risk_judge`（nodes/risk.py）：现有 `check_decision_prices` 调用后，若 anomaly 非空 → 构造打回反馈（逐条 anomaly 的 source_text + 指标名 + 已验证值 + 偏差幅度，措辞同族【决策价位交叉校验打回】）→ `call_llm_for_json` 重出决策恰一次 → 对新终稿**重放 payout self-check**（重试换代可能再引入自算赔率，计数与首次合并不清零）→ 复检 `check_decision_prices` → 写 `decision_price_gate = {result: "pass"|"fail", note, attempts}`；note 语义：「打回后已修正」/「已打回仍未通过：N 条残留」。重试换代后按既有 I-1 模式复核 `final_price_check` note（`_recheck_price_note_after_retry`），不触发新一轮打回（MUST NOT 死循环）。
2. `decision_price_anomalies` 语义收窄：始终保存**最终终稿**的残留 anomaly（修正后为空列表），作为 trace 可观测载体；报告侧消费全部移除。
3. `routing.py` 新增 `after_risk_judge`：`decision_price_gate.result == "fail"` → `"__end__"`，否则 `"fund_manager"`；`graph.py` 将 `risk_judge → fund_manager` 无条件边替换为条件边。回路无环：打回在节点内至多一次，路由无回边。
4. `nodes/report.py`：删除 `_price_anomaly_notes` 及 `_fmt_reeval_triggers`/`_format_trade_decision` 的 anomalies 参数链（report.py:491 调用点同步）；阻断路径下无报告可渲染，标注成为死代码，删除优于保留。
5. `nodes/fund_manager.py`：`FINAL_CHECK_LABELS` 追加 `("decision_price_gate", "决策价位校验")`——gate 通过后的「打回后已修正」复核标注进 FM 上下文（与其他「打回后已申报」同型，全量如实进上下文）；gate fail 时 FM 根本不执行，不存在泄入报告路径。
6. `state.py`：新增 `decision_price_gate: dict` 声明（`test_graph_5layer::TestNodeOutputChannels` 门禁要求节点产出键 ⊆ 声明）；同步修订 `decision_price_anomalies` 的注释（不再是「纯观测不参与路由」）。
7. `api.py` `_run_graph_streaming`：图流正常耗尽且 `report_sent` 为 False 时（try 块内、for 循环之后）→ 按阻断来源构造 failure_reason（`decision_price_gate.result == "fail"` → 含「决策价位交叉校验未通过」与首条 anomaly 摘要；`validation_result == "FAIL"` → 勾稽校验阻断；其余 → 管线结束未产出报告）→ `update_session_status(session_id, "failed", ...)` + yield 既有 `error` 类型 SSE 终态事件。阻断路径下报告/decision_log 均不落（既有代码仅在 report_sent 分支执行）。
8. 故障注入回归测试（评审建议固化）：stub LLM 首次固定输出含错误价位 95 的决策（state 已验证近期低点 = 570），分别断言①打回后修正 → gate pass、放行进 FM；②打回后仍输出 95 → gate fail、`after_risk_judge` 路由 END、报告渲染不含报警文本；③API 层会话置 failed + failure_reason。

**非交互类判定**：纯后端逻辑与会话终态；SSE error 为既有事件类型，前端零改动 → 不适用 §3.5 E2E 门禁与 Step 5 人工验证。

## Alternatives Considered

- **方案 A：代码直接改写错误价位为已验证值（自动修正）**——不选：越参考带的价位改写等于代码替 LLM 做交易决策（`price_level_corrected` 模式仅适用于参考带内修正，是有界特例不是通例）。
- **方案 B：维持放行 + 报告保留标注（现状）**——不选：即评审定性的「带病交付」病灶本体；报警文本进交付物没有读者价值，只有误导价值。
- **方案 C：门禁前置到 validate_trade_prices 层（trader 之后）**——不选：被校验文本在 risk_judge 终稿才定型（风险辩论改写 reasoning/触发条件），前置只能校验 trader 初稿，拦不住终稿引入的错误，还得在 risk_judge 再校验一次，两层打回叠加放大复杂度。
- **方案 D：校验器异常 fail-closed（异常也阻断）**——不选：校验器自身缺陷不应惩罚用户管线；fail-open + 告警日志与全库观测旁路哲学（risk.py 既有 try/except）一致。

## Risks

- **误报拦截好决策**（如合法目标价偏离全部已验证指标）：偏差形态有 2% 阈值 + price_levels 参考带豁免 + 量纲/数量级过滤三重护栏，结构化价位（entry/stop/target）通常锚定参考带，实际暴露面主要是自由文本触发价——而自由文本触发价本就应当锚定已验证水平。打回重试给了一次申辩机会；残留误报经 trace anomaly 明细可人工终裁，阈值/护栏调整走 delta（与「自动化处置只挂在终裁为真错误的桶上」纪律一致）。
- **打回重试额外 LLM 成本**：仅 anomaly 非空时触发一次，与既有三回路同量级；正式批评估口径下可观测（node 调用计数经既有 trace 埋点）。
- **阻断终态误伤正常路径**：API 收尾处理仅在 `report_sent == False` 时触发，正常完成路径有报告必然 report_sent；测试覆盖「正常完成不受影响」反例。
