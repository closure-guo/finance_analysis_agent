# Design: refine-citation-coverage-v3

## Context

`citation_coverage` 首跑 + 20 条人工终裁（2026-09-02 验证报告附录 A，issue #106/#107）暴露：普查把 9 条噪声判黑（模板文本/方向词符号/约数/阈值复述），另有 8 条可校验数字裸奔（state anomalies、比较基期、可重算计算值、1400亿 货币资金口径）。无一条是编造错误。

## Goals / Non-Goals

**Goals:**
- 普查信号干净：A/F/E 类噪声从 unmatched 中消失，unmatched 降到个位数且剩余多为真缺口；
- 可校验数字不再裸奔：B（anomalies）/C（比较基期）/D（可重算计算值）确定性补登记，**验证标准不降**（走与人工申报完全相同的校验路径）；
- 事件数字（G）有明确豁免纪律且可追溯（event_covered 标记）。

**Non-Goals:**
- 不引入 RARR 式"打回 LLM 局部再生"循环（D 类的产出后校验另行评估，本 delta 只做确定性补登记）；
- 不改变校验器容差语义（0.5%/0.01 相对/绝对裁决契约不动，只调普查匹配尺度）；
- 不做跨 Agent 一致性仲裁。

## Decisions

### D1 普查规则修正（citation_coverage.py，issue #106）

1. **模板/脚手架文本排除**：决策语义/position_size 档位说明等结构性文本段不普查。实现：对 `extract_census_numbers` 增加"段落语境"输入——跳过匹配脚手架关键词（档位/仓位/如总资金/决策语义等）的文本区间；清单进 fixture。
2. **方向词符号不敏感**：数字邻近（±N 字符内）方向词（下滑/下降/增长/上升/减少/增加）时，匹配按绝对值进行（10.05% ↔ claim -10.05）。
3. **容差 2%**：普查用独立容差 `CENSUS_TOL = 0.02`（相对），不再复用 `value_close` 的 0.5%；绝对值下限 0.01 保留。
4. **不等式匹配**：数字带「超/约/近/低于/高于/达到」修饰时，改为与 claim 阈值比较（|value − stated| ≤ 2%·stated 视为命中），不再要求等值。

### D2 anomaly 自动补登记（issue #107-B，人工终裁的设计规格）

- **触发双条件**：① 正文数字解析值与某 anomaly 字符串中的数值匹配（取整感知容差）；② 该 anomaly 的指标名（如"净债务/EBITDA"）与数字出现在同一句子/段落。
- **取整感知容差**：补登记 claim 允许 |stated − truth| ≤ 0.5 个百分点（整数取整最大误差）；真错（差 100 个百分点）仍 FAIL。
- **field_ref 指向结构化真值**：`growth_rates.{dim}.{metric}`（浮点真值在 state，compute.py:184 来源），anomaly 字符串**只定位不验证**——防"字符串验字符串"循环验证。
- **反洗白**：state 无对应项的数字（如 LLM 编造的 1400亿 口径）双条件不满足 → 保持 unmatched → 走 reject/复核。
- 实现位置：`citation_node.py` 补登记后处理（对 text 与 state.anomalies + state.growth_rates 做共现匹配，产出补充 Claim 并入校验）。

### D3 comparative 基期值强制建档（issue #107-C）

- `Claim` 已设计 `field_ref_b`/（comparative 基期），本 delta 在 prompt 侧强制：comparative claim 必须声明双端（当期 stated_value + 基期 stated_value_b）；校验器对基期值走与当期相同的容差校验。
- 落地：analysts prompt 补 comparative 双端申报规则 + citation.py comparative 分支校验基期 + fixture 钉死。

### D4 computational 补登记（issue #107-D）

- 对「正文数字 + 可重算指标名共现」（如 FCF 同比 +96.6%），确定性补 computational claim：field_ref 指向可重算指标，交由既有公式重算路径验证。
- 复用 `_COMPUTATIONAL_RECALC` 注册表；不可重算的不补，留 unmatched。

### D5 事件数字豁免（issue #107-G）

- 新闻/事件来源数字（如出厂价 969/1169 元）：允许不建数值 claim，但正文须内联注明来源事件。
- 普查：数字能匹配到 state 事件源（key_events/news 中的数值）→ 标记 `event_covered`，不进 unmatched。
- 首版实现：事件数值匹配（解析 key_events 文本中的数字），无法可靠匹配的事件源数字仍报 unmatched 并在正文缺失来源时提示。

## Risks / Trade-offs

- **普查容差放宽到 2%**：可能放过 1-2% 级的真错值（如声称 91.0 实为 93.0 仍黑，但 91.5 vs 92.0 会认领）。权衡：普查是召回工具，精确定位留给 claim 校验层（0.5% 裁决不变）。
- **自动补登记复杂度**：共现匹配可能误配（指标名撞词）。用双条件 + 取整容差压误配；不满足即退回 unmatched 原流程。
- **prompt 变更**：D3/D5 改 prompt → 需 `deploy_prompts.py` 发布 + prompt 契约测试；eval 门禁会检查 prompt 一致性。
- **范围控制**：D3/D4/D5 涉及 prompt/事件源/公式重算，实现量大于 D1/D2；本 delta 以 D1/D2 为核心交付，D3/D4/D5 按 tasks 顺序推进，无法一次完成的部分保留为 spec 契约 + 待办任务。
