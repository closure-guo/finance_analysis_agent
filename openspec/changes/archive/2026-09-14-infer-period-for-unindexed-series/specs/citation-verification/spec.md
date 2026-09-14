## MODIFIED Requirements

### Requirement: 路径形态归一

field_ref 解析 SHALL 对 DataFrame 行键同时尝试原始值与去连字符形式（`2025-12-31` ↔ `20251231`）；根键为 `quarterly_trend` 且路径段匹配 `\d{4}Q[1-4]` 时 SHALL 查 `quarters` 列表换算为位置索引。**根键别名 SHALL 归一：`derived` → `derived_series`**（analysts context 曾提示简写前缀 `derived.`，与 state 根键不一致——归一面同时覆盖普通解析与计算型注册表查找，两种写法等价）。归一 SHALL 双向幂等，SHALL NOT 改变既有负索引与 `[N]` 括号语义。

**未索引序列的期次定位**：claim 引用序列（如 `quarterly_trend.yoy`）而未带位置索引/季度段时，校验器 SHALL 用「claim `period` 声明值 → 正文（interpretation）唯一期次表述」定位元素，且该推断期次**只用于定位**；`period` 一致性检查 SHALL 仍只比对声明值。正文期次表述在同一优先级上唯一命中时方可采纳（优先级：季度 > 完整日期 > 年月 > 年），多值或无值 SHALL NOT 猜测。**数值型解析路径**（`_resolve_field_ref`）定位仍失败（解析结果为列表/元组且期次不可知）时 SHALL 判 `UNVERIFIABLE` 并计覆盖缺口，SHALL NOT 判 FAIL（数值对错不可知不得判死）；路径本身不可解析（如键不存在）仍判 `FAIL path_unresolvable`。计算型 claim 的未索引序列引用按重算回声命中判定，语义不变。

**其余解析形态归一**：

1. **列名单位后缀**：报表域列名匹配 SHALL 在词表别名归一之外再按「剥尾部括号单位」比对（akshare 指标表真实列名带 `(元)`/`(%)`/`(次)` 等后缀而 claim 常省略，如 `股息发放率(%)` ↔ `股息发放率`）；剥后缀后多列同名 SHALL 判歧义返回不可解析，SHALL NOT 任选。
2. **路径止于列名**（省略行键）：SHALL 取**最新一行**。state 报表 DataFrame 为生产者降序（最新在前——`compute.py` 以 `iloc[0]` 取最新），修复前实现取 `iloc[-1]` 即最旧行。
3. **真值 NaN**：解析结果为 NaN（该期未披露/不适用）时 SHALL 判 `UNVERIFIABLE` 并计覆盖缺口，SHALL NOT 判 `value_mismatch`（nan 参与比较恒为假，会误判 FAIL）。

#### Scenario: 显示格式日期可解析

- **WHEN** claim field_ref 为 `financial_indicators.2025-12-31.加权每股收益`，行键存储为 `20251231`
- **THEN** 解析 SHALL 命中该行

#### Scenario: 季度标签换算位置

- **WHEN** claim field_ref 为 `quarterly_trend.yoy.2026Q2`
- **THEN** 解析 SHALL 经 quarters 列表定位该季度

#### Scenario: 列名单位后缀可省略

- **GIVEN** 真实列为 `股息发放率(%)`（akshare 指标表实测），claim 写 `financial_indicators.2025-12-31.股息发放率`
- **WHEN** 解析该引用
- **THEN** SHALL 命中该列（r2 语料该条判 `path_unresolvable`）
- **AND** 剥后缀后同名的多列 SHALL 判歧义（不任选）

#### Scenario: 省略行键取最新行

- **GIVEN** state 该报表 DataFrame 为生产者降序（最新在前）
- **WHEN** claim 路径止于列名（如 `balance_sheet.货币资金`）
- **THEN** 解析 SHALL 取最新行（`iloc[0]`），SHALL NOT 取最旧行

#### Scenario: 空值真值降级不判死

- **GIVEN** 解析结果为 NaN（如 600519 `股息发放率(%)` 最新期未披露）
- **WHEN** 执行数值校验
- **THEN** 结果 SHALL 为 `UNVERIFIABLE` 且 `coverage_gap=True`
- **AND** SHALL NOT 判 `value_mismatch` FAIL

#### Scenario: 根键别名等价解析

- **WHEN** claim field_ref 为 `derived.chg_5d`（简写根）而 state 根键为 `derived_series`
- **THEN** 解析 SHALL 归一命中该值
- **AND** 计算型 claim 引用 `derived.*` 时 SHALL 同样按 `derived_series` 查重算注册表（不得落 UNVERIFIABLE）

#### Scenario: 正文期次定位裸序列

- **GIVEN** claim field_ref 为 `quarterly_trend.yoy`（无索引段），`period` 字段为空，正文写「2026Q2净利润同比增速36.46%」，state 中 `quarters` 含 `2026Q2`
- **WHEN** 执行校验
- **THEN** 校验器 SHALL 以正文期次定位到该季度元素并比对数值
- **AND** 与带 `period=2026Q2` 声明的同 claim 校验结论一致（r2 真实语料 6 条实测：修复前无声明即 FAIL）

#### Scenario: 期次不可知时降级不判死

- **GIVEN** claim 引用 `quarterly_trend.yoy` 且 `period` 为空、正文无期次表述（或含多个不同期次）
- **WHEN** 执行校验
- **THEN** 校验结果 SHALL 为 `UNVERIFIABLE` 且 `coverage_gap=True`
- **AND** SHALL NOT 判 `FAIL path_unresolvable`

#### Scenario: 正文期次与数值错配仍拦截

- **GIVEN** 正文写「2026Q2同比增长99.9%」而 state 中该季度 yoy 为 36.46
- **WHEN** 执行校验
- **THEN** 校验器 SHALL 判 `FAIL value_mismatch`

### Requirement: 术语与期次一致性校验

Claim SHALL 扩展 `metric_name`（指标枚举，含中文别名到规范键映射）与 `period` 字段。校验器 SHALL 校验：(a) `metric_name` 的规范键等于 field_ref 末端键；(b) `period` 与 field_ref 解析出的期间一致。不一致判 FAIL 并归入独立桶（semantic_term_mismatch / semantic_period_mismatch）。字段为 None（旧数据或未填）时 SHALL 跳过检查并计入覆盖缺口，SHALL NOT 静默 PASS。metric_name 已申报但词表无对应规范键（词表外）时 SHALL 同样跳过术语检查并计入覆盖缺口——state 指标段空间开放（报表行名/dupont/health_score/garp 等），词表不可闭合，词表外判 FAIL 经三标的冒烟实证全为误报（2026-09-01）。

**根域序列键别名**：`quarterly_trend` 根域的序列键 SHALL 按该域别名表判定术语——`net_profit`（口径为归母净利润单季）接受规范键「归母净利润」与「净利润」。别名表 SHALL 限定于该根域，SHALL NOT 合并全局「净利润」/「归母净利润」规范键（利润表域二者为不同行，合并将放开张冠李戴）。

**术语包含（脚本体边界）**：申报名与引用段互为包含且**断点在中西文边界**时 SHALL 判术语一致——`FCF` ⊂ `FCF收益率`、`ROE` ⊂ `加权ROE`（r4 真实语料两条：数值与真值一致却判 semantic_term_mismatch）。同一文种内部的包含 SHALL NOT 豁免：`MA` ⊂ `MACD` 是不同指标，仍判张冠李戴。

#### Scenario: 术语张冠李戴被拦截

- **GIVEN** claim 的 field_ref 指向 `profitability_metrics.毛利率.2024`，metric_name 为"净利率"
- **WHEN** 执行校验
- **THEN** 判 FAIL，桶为 semantic_term_mismatch（即使数值与真值一致）

#### Scenario: 缺省字段显式降级

- **WHEN** claim 缺 metric_name/period（旧格式）
- **THEN** 跳过对应检查，计入覆盖缺口计数，其余检查照常

#### Scenario: 词表外术语显式降级

- **GIVEN** claim 申报了 metric_name，但词表无其规范键（如 "健康度评分" 之于 `health_score.total`）
- **WHEN** 执行术语检查
- **THEN** 跳过术语检查，计入覆盖缺口计数，SHALL NOT 判 FAIL；值级/期次/内部一致性检查照常

#### Scenario: 季度趋势域净利润术语接受

- **GIVEN** claim field_ref 为 `quarterly_trend.net_profit.0`，metric_name 为「净利润」，数值与真值一致（r4 真实语料：招行 385.93 亿元）
- **WHEN** 执行术语检查
- **THEN** SHALL 判术语一致，SHALL NOT 判 semantic_term_mismatch

#### Scenario: 利润表域净利润不互认

- **GIVEN** claim field_ref 指向利润表列「归属于母公司的净利润」，metric_name 为「净利润」，且该列真实存在
- **WHEN** 执行术语检查
- **THEN** 术语检查结论 SHALL 与修复前一致（真实列名规则照常生效；根域别名 SHALL NOT 把「净利润」放行到归母列之外的报表行）

#### Scenario: 脚本体边界包含接受

- **GIVEN** claim field_ref 为 `cashflow_metrics.FCF收益率.2025` 而 metric_name 为「FCF」（或 `financial_indicators.…加权净资产收益率` 而 metric_name 为「ROE」）
- **WHEN** 执行术语检查
- **THEN** SHALL 判术语一致，SHALL NOT 判 semantic_term_mismatch

#### Scenario: 同文种包含不豁免

- **GIVEN** claim field_ref 为 `technical_indicators.MACD.DIF.-1` 而 metric_name 为「MA」
- **WHEN** 执行术语检查
- **THEN** SHALL 维持 FAIL（semantic_term_mismatch）

