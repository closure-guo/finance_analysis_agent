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

### Requirement: 性能度量采集

评估链路 SHALL 从 Langfuse trace 聚合每次分析的端到端时延、节点时延分解、token 用量与折算成本，quick/deep 分开统计；模型单价表配置化。

#### Scenario: 度量聚合

- **WHEN** 评测运行完成
- **THEN** 报告含性能一节：两种模式的时延/token/成本汇总与节点分解

### Requirement: 基线对比与回归门禁

系统 SHALL 在 docs/evals/ 维护性能基线档案，评测对比基线；时延或成本超基线配置百分比即告警或失败。

#### Scenario: 回归拦截

- **WHEN** 端到端时延或成本超基线阈值
- **THEN** 门禁按配置告警或失败，报告标注退化维度

### Requirement: 趋势追踪

nightly 运行 SHALL 沉淀性能时序数据，识别单次不超阈值但趋势向上的缓慢劣化。

#### Scenario: 趋势识别

- **WHEN** 连续 N 轮（配置化）指标单调劣化且累计幅度超阈值
- **THEN** 报告标注趋势告警，即使单轮未触发门禁

### Requirement: 在线 hosted evaluator

系统 SHALL 对生产 trace 启用 Langfuse managed evaluator（采样率配置化，默认 10%），维度对齐离线评测口径；自托管版本不支持时降级为轮询脚本方案。

#### Scenario: 采样打分

- **WHEN** 生产 trace 到达且命中采样
- **THEN** hosted evaluator 输出分数，与离线评分入同一分数命名空间并可按来源区分

### Requirement: 口径对齐验证

系统 SHALL 抽样比对 hosted 与离线 judge 对同一 trace 的打分差异，差异超阈值时告警。

#### Scenario: 口径漂移告警

- **WHEN** 同 trace 两套打分 MAE 超配置阈值
- **THEN** 报告标注口径漂移，提示统一裁判口径

### Requirement: 在线质量告警

hosted 均分跌破阈值 SHALL 触发告警（Langfuse webhook 或轮询脚本）；evaluator 模板作为 prompt 纳入版本管理与部署纪律。

#### Scenario: 均分告警

- **WHEN** 滑动窗口内 hosted 均分低于配置阈值
- **THEN** 产生告警并输出低分 trace 清单

### Requirement: 人工标注工具

系统 SHALL 提供标注脚本：从 Langfuse 抽样 trace 导出评判表（维度 × 人工 1-5 分），支持多轮标注与仲裁，样本集落 tests/fixtures/。

#### Scenario: 抽样导出

- **WHEN** 运行标注导出脚本并指定抽样规模与模式（quick/deep）
- **THEN** 生成含 trace 摘要与空人工评分列的标注表

### Requirement: judge-人工一致性指标

系统 SHALL 计算 judge 分 vs 人工分的 Spearman 相关、MAE、方向一致率，输出校准报告至 reports/。

#### Scenario: 一致性报告

- **WHEN** 标注完成并运行一致性计算
- **THEN** 报告给出三项指标，低于配置阈值时标记需修订 judge prompt

### Requirement: 校准触发与归档

judge prompt 变更后 SHALL 必跑一致性校准；校准结论归档至 docs/evals/。

#### Scenario: 变更后强制校准

- **WHEN** judge prompt 经部署管线发布新版本
- **THEN** 下一轮评测强制附带一致性校准，结论归档

