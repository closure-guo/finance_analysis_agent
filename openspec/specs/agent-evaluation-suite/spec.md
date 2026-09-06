# agent-evaluation-suite Specification

## Purpose
TBD - created by archiving change add-toolcall-evaluation. Update Purpose after archive.
## Requirements
### Requirement: 工具调用轨迹提取

评估链路 SHALL 从 Langfuse trace 提取工具调用序列（工具名/参数/耗时/成败/重试次数）作为评估输入。

#### Scenario: 轨迹提取

- **WHEN** 评测样本为 quick 模式 trace 且含工具调用
- **THEN** 输出结构化调用序列，含失败与重试标注

### Requirement: 工具调用评估维度

评估体系 SHALL 覆盖：工具选择正确性（合法集合断言，非唯一序列）、参数合法性、调用效率（冗余/循环检测）、失败恢复（失败后换策略）。

#### Scenario: 合法集合断言

- **WHEN** 样本声明了合法工具集合且实际调用落在集合内
- **THEN** 工具选择维度通过，不因与 golden 序列不同而误判失败

#### Scenario: 循环调用检测

- **WHEN** 同一工具以相同参数连续调用超过配置上限
- **THEN** 调用效率维度扣分并在报告标注

### Requirement: 工具调用门禁

工具调用维度 SHALL 纳入评测门禁（回归阈值），@live nightly 防漂移。

#### Scenario: 回归拦截

- **WHEN** 工具调用维度均分跌破基线阈值
- **THEN** 门禁失败并输出退化样本清单

### Requirement: 事实性 claim 抽取

评估链路 SHALL 从最终报告抽取可验证 claim（数值型：价格/涨跌幅/财务指标；事实型：事件/日期/主体）。

#### Scenario: claim 抽取

- **WHEN** 评测样本含最终报告文本
- **THEN** 输出结构化 claim 列表，每条标注类型与文中位置

### Requirement: 证据校验与幻觉率

系统 SHALL 将 claim 对照证据源（K 线/财报真实数据 + 检索内容）判定 supported/contradicted/unverifiable；`hallucination_rate` = contradicted / 可验证 claim 总数，unverifiable 单列不进分子。

#### Scenario: 矛盾识别

- **WHEN** 报告中数值 claim 与真实数据矛盾（超出容差）
- **THEN** 计为 contradicted 并计入幻觉率分子

#### Scenario: 合理推断不惩罚

- **WHEN** claim 无法从证据源证实亦不矛盾
- **THEN** 计为 unverifiable 单列，不影响幻觉率

### Requirement: 幻觉率门禁

幻觉率上限 SHALL 纳入评测门禁并 nightly 追踪趋势。

#### Scenario: 超限拦截

- **WHEN** hallucination_rate 超过配置上限
- **THEN** 门禁失败并输出 contradicted claim 清单

