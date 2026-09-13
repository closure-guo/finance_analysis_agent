# Delta for citation-verification

## MODIFIED Requirements

### Requirement: 计算型声明重算注册表全覆盖

计算型 claim 的重算注册表 SHALL 覆盖 `metrics/` 模块的全部纯函数指标族（偿债、盈利、运营、现金流、杜邦、技术指标、风控指标）**以及全部由代码从数据快照计算的派生字段（含 `garp_result`、`anomalies`）**，每个注册根键 SHALL 有独立的重算 fixture 测试（从原始报表数据重算，不依赖 LLM、不调外部接口）。字符串枚举型派生字段（如 GARP failures 集合）SHALL 按集合相等比对。未注册根键的计算型 claim SHALL 判 UNVERIFIABLE，且 SHALL 计入覆盖缺口指标供覆盖率审计。
(Previously: 未覆盖快照派生字段——r2 实测 garp_result 5/5、anomalies、空值比率字段共约 23 条恒为 UNVERIFIABLE)

#### Scenario: 已注册指标重算通过

- **GIVEN** Agent 报告含计算型 claim（如 `solvency_metrics.资产负债率.2024`），其根键已注册
- **WHEN** 执行校验
- **THEN** 系统 SHALL 从 state 原始数据经对应纯函数重算 ground-truth，按相对容差 0.5% 判定 PASS/FAIL

#### Scenario: 未注册根键显式降级

- **WHEN** 计算型 claim 的根键未在注册表中
- **THEN** 校验结果 SHALL 为 UNVERIFIABLE
- **AND** 该事件 SHALL 计入覆盖缺口计数，SHALL NOT 静默等同于 FAIL 或被忽略

#### Scenario: 容差语义不回归

- **WHEN** 注册表扩展后执行任意校验
- **THEN** 数值容差（绝对 0.01 / 相对 0.5%）与三态裁决（PASS/FAIL/UNVERIFIABLE）语义 SHALL 与既有契约一致

#### Scenario: 快照派生字段可验

- **WHEN** Agent 报告含 `garp_result`、`anomalies` 等快照派生字段的 claim
- **THEN** 校验 SHALL 经注册的重算/集合比对得出 PASS/FAIL，SHALL NOT 恒为 UNVERIFIABLE

## ADDED Requirements

### Requirement: 数值单位量级归一

数值比对 SHALL 在容差比较前进行单位归一：优先从 claim 的 interpretation 文本中提取与 stated_value 面值相同 token 的紧邻单位词（亿/万/元），按 1e8/1e4/1 缩放后与真值比较；interpretation 无单位词时，truth/stated 比值落在 1e4 或 1e8 的相对容差带内 SHALL 判 PASS 并标记 `unit_inferred`；数据根键 SHALL 注册 `unit` 属性（元/万元/%/无量纲），真值先按表单位归一。有单位词且缩放后仍不匹配 SHALL 维持 FAIL。

#### Scenario: 亿元申报对元真值通过

- **WHEN** claim stated_value=583.95、interpretation 含「583.95亿元」、真值 5.8394610072e10（元）
- **THEN** 校验 SHALL 判 PASS 并标记 unit_normalized="亿"

#### Scenario: 无单位词比值兜底

- **WHEN** interpretation 不含单位词且 truth/stated ≈ 1e4 或 1e8（相对容差内）
- **THEN** 校验 SHALL 判 PASS 并标记 unit_inferred

#### Scenario: 缩放后仍不匹配维持 FAIL

- **WHEN** 单位缩放后与真值的偏差超出容差
- **THEN** 校验 SHALL 维持 value_mismatch FAIL

### Requirement: 路径形态归一

field_ref 解析 SHALL 对 DataFrame 行键同时尝试原始值与去连字符形式（`2025-12-31` ↔ `20251231`）；根键为 `quarterly_trend` 且路径段匹配 `\d{4}Q[1-4]` 时 SHALL 查 `quarters` 列表换算为位置索引。归一 SHALL 双向幂等，SHALL NOT 改变既有负索引与 `[N]` 括号语义。

#### Scenario: 显示格式日期可解析

- **WHEN** claim field_ref 为 `financial_indicators.2025-12-31.加权每股收益`，行键存储为 `20251231`
- **THEN** 解析 SHALL 命中该行

#### Scenario: 季度标签换算位置

- **WHEN** claim field_ref 为 `quarterly_trend.yoy.2026Q2`
- **THEN** 解析 SHALL 经 quarters 列表定位该季度

### Requirement: 术语一致性以真实列名为准

根键为 DataFrame 报表域（三大报表、financial_indicators）的 claim，其 metric_name 与解析出的真实列名一致时 SHALL 判术语一致；`metric_vocab` SHALL 维护报表列名到规范名的别名映射（如「归属于母公司的净利润」→「归母净利润」）。

#### Scenario: 照抄真实列名通过

- **WHEN** claim metric_name 为「归属于母公司的净利润」且该列真实存在于利润表
- **THEN** 语义核对 SHALL 判一致，SHALL NOT 判 semantic_term_mismatch

### Requirement: 符号校验限定有符号量

指标注册表 SHALL 为每个指标声明 `signed` 属性（增长率/同比环比/变动幅度/技术柱状等为 True；指数/比率/价格等水平量为 False）。`direction` 申报 SHALL 仅在 signed 指标上参与符号比对；非 signed 指标上的 negative/positive 申报 SHALL 记覆盖缺口，SHALL NOT 判 direction_mismatch。分析师 prompt 中 `direction` 字段 SHALL 注明「符号语义，非高低」。

#### Scenario: 水平量的负向申报不判 FAIL

- **WHEN** claim 为「PMI 49.8 低于荣枯线 50」，metric 注册 signed=False，direction 申报为 negative
- **THEN** 校验 SHALL 记覆盖缺口提示，SHALL NOT 判 direction_mismatch FAIL

#### Scenario: 有符号量方向照常校验

- **WHEN** claim 为增长率类（signed=True），direction=positive 而真值为负
- **THEN** 校验 SHALL 维持 direction_mismatch FAIL

### Requirement: 文本 claim 分型与回声匹配

`claim_type ∈ {entity, regulatory}` 或 `source_type = event` 的文本 claim SHALL 不计入 FAIL=0 分母、SHALL 不计覆盖缺口；校验 SHALL 先做回声匹配（claim/interpretation 归一后与 `news_list[*].title`、`key_events[*]` 子串匹配），命中判 PASS(echo)，未命中判 UNVERIF​IABLE(text) 并单独计数。

#### Scenario: 标题回声命中

- **WHEN** 文本 claim 引用的新闻标题（归一后）出现在 news_list 标题中
- **THEN** 校验 SHALL 判 PASS(echo)

#### Scenario: 未命中不污染分母

- **WHEN** 文本 claim 回声未命中
- **THEN** 校验 SHALL 判 UNVERIFIABLE(text)、单独计数，SHALL NOT 计入阻断分母或覆盖缺口

### Requirement: 门禁三层分置与指标拆报

引用门禁 SHALL 分三层：阻断层 = 归一与准入规则后残余 FAIL 计数（`citation_blocked`，>0 阻断）；警告层 = coverage < 0.90 报警不阻断；跟踪层 = UNVERIFIABLE 占比（分文本/未注册两类单独计数）。`citation_minor_fail` SHALL 退役。实验报告与 trace SHALL 分别输出残余 FAIL 数、归一后由 FAIL 转 PASS 数（`verifier_normalized_count`）、文本/未注册 UNVERIFIABLE 数，SHALL NOT 单独呈现混合 `citation_pass` 作为引用质量指标。

#### Scenario: 归一后残余 FAIL 阻断

- **WHEN** 归一后仍存在准入规则内的 FAIL
- **THEN** 阻断层 SHALL 置位，管线按既有渲染路径放行但标记阻断

#### Scenario: 覆盖率不足报警不阻断

- **WHEN** coverage < 0.90 且无残余 FAIL
- **THEN** 系统 SHALL 记录警告标记，SHALL NOT 阻断

#### Scenario: 拆报输出

- **WHEN** 一轮实验结束
- **THEN** 报告 SHALL 含残余 FAIL 数、verifier_normalized_count、文本/未注册 UNVERIFIABLE 数，SHALL NOT 呈现单一混合通过率

### Requirement: 注入式故障演练

归一上线 SHALL 以注入式故障验证门禁仍会开火：对真实 fixture 故意改错一个数字（非单位换算、非路径/格式差异），校验 SHALL 判 FAIL 且阻断层置位。该演练 SHALL 作为回归测试长期保留。

#### Scenario: 注入真错误仍开火

- **WHEN** 对 fixture 中的 income_statement 营收真值注入 ±10% 偏差并生成对应 claim
- **THEN** 校验 SHALL 判 value_mismatch FAIL，阻断层置位
