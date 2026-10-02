# Delta for price-level-tooling

## MODIFIED Requirements

### Requirement: 决策文本价位与已验证技术指标交叉校验

决策层产出的自由文本价位（`reeval_triggers` 条目与 `inaction_reason`/`reasoning` 中出现的数值价位）SHALL 由确定性代码与 state 中已验证的技术指标值（最新收盘价、各周期 MA、近期高低点、布林轨道）交叉核对，MUST NOT 仅因数值出现在决策文本即视为可信。以下两种形态 SHALL 各登记一条 anomaly（复用既有 anomalies 通道，附原始文本片段与最接近的已验证指标值）：

- **偏差形态**：文本价位与语义最接近的已验证指标值偏差超过配置阈值（默认 2%），且不落在 `price_levels` 参考带内；
- **空洞形态**：上破类触发（「站上/突破/收复 X」）中 X 不高于最新收盘价，或下破类触发（「跌破/回落至 X」）中 X 不低于最新收盘价——即触发条件在当前时点已经满足，不构成有效的再评估门槛。

anomaly 的处置 SHALL 为门禁语义（2026-10-02 回归评审裁决，取代「纯观测 + 报告旁注」）：

- risk_judge 校验出非空 anomaly 时，SHALL 携 anomaly 明细（原始文本片段、指标名、已验证值、偏差幅度）**定向打回重试一次**，要求修正文本价位后重新输出完整决策 JSON；
- 重试输出修正（复检无 anomaly）→ 决策放行进 Fund Manager 审批，gate 结果与「打回后已修正」复核标注落 state；
- 重试后仍存在 anomaly → 管线 SHALL 阻断：MUST NOT 进入 Fund Manager 审批、MUST NOT 产出报告，阻断原因与 anomaly 明细落 state/Langfuse trace；
- 报警信息属于内部 trace：报告 SHALL NOT 渲染「价位待核实」类标注（无论打回修正与否），anomaly 明细仅经 state/Langfuse trace 可观测。

无法与任何已验证指标建立归属对应的数值（如财报降幅阈值、赔率比值）SHALL NOT 被误报——归属匹配 SHALL 区分价格量纲与百分比/比值量纲。校验器自身抛出异常时 SHALL fail-open（放行决策并告警日志），MUST NOT 因校验器缺陷阻断管线；校验器无任何已验证指标可核对时 SHALL 直通（不凭空报 anomaly）。

#### Scenario: 偏差异常打回后修正放行

- **GIVEN** risk_judge 终稿的 `reeval_triggers` 含文本价位 95，state 已验证指标中近期低点 = 570（偏差 83.33%，超过 2% 阈值且不在 price_levels 参考带内）
- **WHEN** `check_decision_prices` 登记偏差形态 anomaly
- **THEN** risk_judge SHALL 以该 anomaly 明细（含已验证值 570）构造打回反馈，重试输出完整决策 JSON 恰一次
- **WHEN** 重试输出的复检无 anomaly
- **THEN** 决策 SHALL 放行进入 fund_manager 审批，gate 结果记「打回后已修正」
- **AND** 最终报告 MUST NOT 出现「价位待核实」标注或任何报警文本

#### Scenario: 打回后仍异常阻断交付

- **GIVEN** 首次校验登记 anomaly 且打回重试已执行
- **WHEN** 重试输出的复检仍存在 anomaly（如 stub LLM 固定输出错误价位 95）
- **THEN** 管线 SHALL NOT 进入 fund_manager 审批节点，SHALL NOT 产出最终报告
- **AND** 阻断原因与残留 anomaly 明细 SHALL 落 state（Langfuse trace 可查）
- **AND** 会话终态处置符合 pipeline-events「管线阻断终态可见化」

#### Scenario: 空洞形态同门禁处置

- **WHEN** `reeval_triggers` 含「价格放量站上止损参考带上沿 22.61」而最新收盘价 23.03（上破条件已满足，空洞形态）
- **THEN** 该 anomaly SHALL 与偏差形态同处置：打回重试一次 → 仍异常阻断、修正放行

#### Scenario: 无异常直通

- **WHEN** 决策文本价位与已验证指标偏差在阈值内且方向语义有效（如「跌破近期低点 22.94」且现价 23.03）
- **THEN** SHALL 不产生 anomaly、不触发打回，决策照常进入审批（行为与现状一致）

#### Scenario: 校验器自身异常 fail-open

- **WHEN** `check_decision_prices` 自身抛出异常（校验器缺陷或 state 形态噪声）
- **THEN** 管线 SHALL 放行决策（fail-open）并记录告警日志
- **AND** 决策照常进入审批，MUST NOT 因校验器异常阻断

#### Scenario: 非价格量纲数值不误报

- **WHEN** `reeval_triggers` 含「单季净利降幅收敛至 18.35% 以下」「赔率修复至 1:1」等百分比/比值表述
- **THEN** 归属匹配 SHALL 识别其为非价格量纲，SHALL NOT 按价位偏差误报 anomaly
