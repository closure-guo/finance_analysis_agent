# Design: add-period-key-citation-validation

## Approach

三段式实现，全部落在 `citation.py` 校验管线内，不改 Claim schema（`period` 字段已存在）：

1. **索引构建** `_build_value_period_index(state) -> dict[float, set[str]]`：遍历序列型指标段（`profitability_metrics`/`solvency_metrics`/`efficiency_metrics`/`cashflow_metrics` 为 `{指标: {期次: 值}}` 两层结构；`quarterly_trend.gross_margin` 等 list 配 `quarters` 对齐），float 归一后入索引，值为 set[期次段]。索引按 state 惰性缓存于校验入口（verify_claims 单次调用内构建一次）。
2. **期次标记抽取** `_extract_period_markers(text) -> set[str]`：正则抓 `YYYY`、`YYYYQn`、`年报/中报/季报/单季/Q[1-4]` 中文形态，经 `normalize_period` 归一；归一失败的词忽略（与「不误伤」纪律一致）。
3. **消歧判定**（`_check_period_disambiguation`，挂 `_check_period` 之后）：
   - 撞车判定先行：stated_value 在索引中锚点期次基数 ≥2 才进入消歧档
   - 撞车档：interpretation 期次标记集合须含 field_ref 溯源期次——不含且标记非空 → FAIL `semantic_period_mismatch`（v4 形态）；标记为空 → FAIL `ambiguous_value_undisambiguated`
   - 降级边界（三重不误伤，均有实证）：
     - 比较型豁免（field_ref_b / claim_type=comparative）——interpretation 必含基期标记，双端申报结构自担期次语义
     - interpretation 为空（旧格式）跳过——义务针对正文标注，正文缺席不判（benchmark 合成语料实证：state_v1 资产负债率 2022/2024 合成撞车 40.0 误判 FAIL）
     - 唯一锚点跳过认领检查——「自 2021 年 4.30 次缓慢下行」类历史参照表述自由（002412 真实语料实证误伤后修正）
   - 方案演进：首版对全部单值 claim 查标记认领（含唯一锚点），真实语料回归暴露历史参照误伤后收敛为「认领检查仅撞车档」——构造场景让位于实证语料

## Alternatives Considered

- **方案 A：只对歧义值做标记检查**——实现最窄，但 v4 案例的实质风险（正文期次语境与登记期次错配）在非撞车值上同样存在（Scenario: 标记错配检查独立于值歧义），只查歧义值会漏。
- **方案 B：全量校验 interpretation 不得出现 field_ref 之外的期次**——会误伤比较型 claim（「较 2024 年提升至…」是合法表述）。放弃。
- **本方案 C：只要求 field_ref 期次被认领**——语义最小且对称：有标记则须认领，歧义则必须认领；提及别的期次自由。

## Risks

- **误伤存量语料**：r2/r4 语料可能有「较 YYYY」比较型表述。对策：只要求 field_ref 期次 ∈ 标记集合；全量语料回归是硬验收项（Scenario 已写）。
- **期次标记抽取漏检**（如「前三季度」）：漏检时降级为「无标记」路径——唯一锚点不受影响，歧义值被拦后走定向重试由 LLM 自行补标注，安全侧倾斜。
- **索引遍历开销**：state 两层遍历 + float 归一，每次校验 O(指标数×期次数)，量级千以内，且单次 verify 构建一次。
- **quarterly_trend 键形态**：期次段取 `quarters[idx]`（如 "2026Q2"），与年报键 "2024" 的归一走 `normalize_period` 现有词表；若单季期次串归一失败则该锚点不入索引（不误伤优先）。
