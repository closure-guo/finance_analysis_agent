# citation-verification Delta

## ADDED Requirements

### Requirement: claim direction 独立申报与方向一致性校验

Claim SHALL 增加 `direction` 字段（`"positive" | "negative" | "flat" | None`），数值型（numerical/computational）claim 的 direction 由分析师在登记时显式申报，方向语义 SHALL NOT 由校验器在正文文本中推断。当 direction 已申报时，校验器 SHALL 校验方向一致性：`sign(stated_value) × direction 与 sign(ground_truth)` 不符 → 判 FAIL，分桶为 `direction_mismatch`（新增桶，纳入 value_mismatch 同级的定向重试目标）。当 direction 为 None（旧格式 claim），校验器 SHALL 跳过方向检查并将该 claim 计入覆盖缺口（显式降级，SHALL NOT 静默 PASS），与 metric_name/period 未申报的既有降级先例一致。

#### Scenario: 方向申报与真值不符判 FAIL

- **WHEN** claim 申报 `stated_value=10.05, direction="negative"`，而 field_ref 真值为 `-10.05`
- **THEN** 校验器 SHALL 判 PASS（绝对值匹配且符号经 direction 修饰后一致）

- **WHEN** claim 申报 `stated_value=10.05, direction="positive"`，而 field_ref 真值为 `-10.05`
- **THEN** 校验器 SHALL 判 FAIL 且 bucket 为 `direction_mismatch`

#### Scenario: 旧格式 claim 显式降级

- **WHEN** claim 的 direction 为 None 且正文方向词表兜底未命中
- **THEN** 校验器 SHALL 跳过方向检查、按既有数值容差判定，并将该 claim 计入覆盖缺口（coverage_gap），SHALL NOT 判 PASS 后静默不计

### Requirement: 方向词表退役为未申报兜底

正文覆盖率普查的方向词符号不敏感匹配（`_DIRECTION_WORDS`）SHALL 仅在 claim 未申报 direction 时作为兜底启用；已申报 direction 的 claim SHALL NOT 再依赖文本方向词推断。兜底词表 SHALL 补充语料实证的高频漏网词：`负增长`、`跌幅`、`收窄`（词表由 11 词扩至 14 词后冻结，后续长尾由 coverage 打回回路兜底，SHALL NOT 无评估依据继续扩表）。

#### Scenario: 已申报 claim 不走词表

- **WHEN** claim 已申报 direction="negative" 且 stated_value 绝对值与真值匹配
- **THEN** 校验器 SHALL 直接按 direction 判定，SHALL NOT 因正文方向词未命中而 FAIL 或计缺口

#### Scenario: 未申报 claim 走兜底词表

- **WHEN** claim direction=None，正文写「营收负增长 5.2%」且真值为 -5.2
- **THEN** 兜底词表 SHALL 命中「负增长」触发符号不敏感匹配，该数字 SHALL 认领成功
