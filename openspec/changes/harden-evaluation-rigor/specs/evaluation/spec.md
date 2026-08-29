# evaluation Specification Delta

## ADDED Requirements

### Requirement: 断言级校验基准集

系统 SHALL 维护断言级校验基准集（claim benchmark）：从历史报告抽样 30-50 份，每份抽取 20-30 条 claim，人工标注每条 claim 的应有裁决（PASS / FAIL / UNVERIFIABLE）。标注 SHALL 双人背对背进行、分歧仲裁，并报告一致性系数（Cohen's κ）。基准集 SHALL 随生产 bad case 滚动补库，SHALL NOT 一次建成后冻结。

#### Scenario: 基准集构建

- **WHEN** 构建或扩充校验基准集
- **THEN** 每条 claim SHALL 有两名标注者的独立标注与仲裁后的最终标签
- **AND** 数据集元信息 SHALL 记录标注者一致性 κ 与版本号

#### Scenario: 滚动补库

- **WHEN** 生产中发现校验器误判的 bad case（人工复核确认）
- **THEN** 该 claim SHALL 以人工裁决为标签补入基准集下一版本

### Requirement: 校验器准度测量与门禁

系统 SHALL 提供校验器准度测量：对基准集运行 `verify_claims`，输出整体 Precision / Recall / F1，以及两个对抗子集的分项召回——(a) 擦边子集：stated_value 在真值 ±5% 以内的对抗 claim；(b) hedged 措辞子集：含"约""可能""接近"等模糊措辞的 claim。校验器整体 F1 ≥ 0.90 为可信门禁；擦边子集召回 SHALL 单独显式披露（不设硬门禁），以暴露近边界盲区。

#### Scenario: 准度达标

- **GIVEN** 基准集标注完成
- **WHEN** 运行准度测量
- **THEN** 报告 SHALL 含整体 P/R/F1（带 95% CI）与两个对抗子集的分项召回
- **AND** 整体 F1 ≥ 0.90 时校验器准度状态为"可信"，否则其下游 FAIL 判定 SHALL 在评估报告中标注"校验器自身准度未达标"

#### Scenario: 擦边盲区披露

- **WHEN** 生成准度报告
- **THEN** 擦边子集召回 SHALL 单独成行披露，SHALL NOT 被整体指标掩盖

### Requirement: 实验对比统计显著性

`run_experiment` 的基线对比 SHALL 使用配对 bootstrap（B=10,000，按 dataset item 重采样）报告差值的 95% 置信区间。当 CI 含 0 时，结论 SHALL 只能表述为"无显著差异"，SHALL NOT 用语义化措辞包装点估计差异。本条适用于全部确定性评估器与 judge 分数的对比报告。

#### Scenario: 显著改进

- **GIVEN** 新 prompt 版本与基线各跑完全量 dataset
- **WHEN** 分数差值的 95% CI 不含 0 且为正
- **THEN** 报告 SHALL 判定"显著改进"并给出 CI 区间

#### Scenario: 差异不显著

- **WHEN** 分数差值的 95% CI 含 0
- **THEN** 报告 SHALL 输出"无显著差异"，并 SHALL NOT 出现"略有提升""整体更好"等无统计支撑的结论性措辞

### Requirement: 数据对齐消融实验

系统 SHALL 支持数据对齐消融：构造三个架构变体——(a) 单分析师直出、(b) 分析师 + Bull/Bear 辩论、(c) 完整 5 层——所有变体接收**完全相同**的 state 快照（fetch_data / compute_metrics 输出重放），仅 Agent 编排不同。每变体 × 每标的 SHALL 重复运行 3 次取中位数。消融报告 SHALL 以 citation_pass 率与 judge 分数（带 CI）衡量各层增量价值，SHALL NOT 用单变体单次运行下结论。

#### Scenario: 变体输入对齐

- **WHEN** 执行消融实验
- **THEN** 三个变体的数据输入 SHALL 来自同一 trace 的 state 快照重放，差异只可归因于编排架构

#### Scenario: 消融结论

- **WHEN** 消融完成
- **THEN** 报告 SHALL 给出每个新增层级的增量效果及 95% CI
- **AND** 对 CI 含 0 的层级，报告 SHALL 明确标注"该层价值未获统计支持"，供成本裁剪决策参考
