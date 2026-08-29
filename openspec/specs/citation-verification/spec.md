# citation-verification Specification

## Purpose
TBD - created by archiving change fix-citation-contract-diseases. Update Purpose after archive.
## Requirements
### Requirement: 序列引用负索引语义

引用校验器对序列型 field_ref SHALL 支持负索引（-1 = 最新一期，-N = 倒数第 N 期），该语义与序列长度及上下文裁剪窗口解耦。技术指标 context 的窗口说明 SHALL 明示负索引约定（"field_ref 引用序列值时用负索引：-1=最新一期"）。正索引按底层序列原位解析（legacy 语义不变）。

#### Scenario: 负索引解析为最新值

- GIVEN state 中某指标序列为升序时间序列且任意长度
- WHEN claim 的 field_ref 以 `-1` 索引该序列（如 `technical_indicators.MA.5.-1`）
- THEN 校验器 SHALL 取序列最后一个元素作为 ground truth

#### Scenario: 裁剪窗口变更不影响校验语义

- GIVEN 分析师 context 的序列裁剪窗口从 60 期调整为任意值
- WHEN LLM 按负索引约定引用序列值
- THEN 校验结果 SHALL 不因窗口变更而改变（负索引与长度无关）

### Requirement: 上下文与校验单一词表

分析师 context 的数据段标题 SHALL 内联标注对应 state 英文键（如「利润表（income_statement，近3年）」），使 LLM 生成的 field_ref 与校验器解析的键天然同源；校验器 SHALL NOT 维护中文标签映射表。引用校验器 SHALL 支持 DataFrame 的「行键.列名」两段解析（行键按单元格值匹配，列名须为真实列）与 `[N]` 括号索引展开。

#### Scenario: 英文键引用可解析

- GIVEN context 段落标题含英文 state 键标注
- WHEN LLM 以该英文键为 field_ref 根键引用数据（含 DataFrame 行键.列名与 `[N]` 括号索引）
- THEN 校验器 SHALL 按对应 state 结构解析出 ground truth

#### Scenario: 中文标签不再是可解析词表

- GIVEN field_ref 根键为未标注进 context 英文键体系的中文标签
- WHEN 校验器解析该引用
- THEN SHALL 按不可路径处理（FAIL），不静默映射

### Requirement: 数值型相对容差

数值型 claim 的 PASS 判定 SHALL 为 |delta| < 0.01 或相对误差 < 0.5%（与计算型容差对齐），消除大数量级数值的假阴性。(Previously: data-ordering-citation-contract（archive）约定校验算法不变，数值型为绝对容差 0.01)

#### Scenario: 亿元级数值四舍五入通过

- GIVEN ground truth 为 1,038,756,658.94 量级的数值
- WHEN stated_value 与其相差 0.5（远小于 0.5% 相对误差）
- THEN 校验 SHALL PASS

#### Scenario: 显著偏离仍失败

- GIVEN ground truth 为任意数值
- WHEN stated_value 相对误差 ≥ 0.5% 且绝对差 ≥ 0.01
- THEN 校验 SHALL FAIL

