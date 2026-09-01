# evaluation Specification Delta

## ADDED Requirements

### Requirement: 基准集 v1.1 构造规则

校验基准集 v1.1 SHALL 重构 near_miss 子集：篡改幅度改为 ±{0.3%, 0.5%, 0.7%, 1%} 四档（探容差边界而非远离边界），且其中 50% 为 should_pass 样本（篡改幅度在容差内，标签为 PASS），使子集同时测量漏检与误报。v1.1 SHALL 新增 semantic_mismatch 子集：数值与 field_ref 正确但术语或期次张冠李戴（如毛利率写作净利率、年报值描述为季度值），标签为 FAIL。子集检出率 SHALL 在准度报告中单独披露。

#### Scenario: 边界双向探测

- **WHEN** 生成 v1.1 near_miss 子集
- **THEN** 样本覆盖容差两侧（0.3%/0.5% 档多为 should_pass，0.7%/1% 档多为 should_fail）
- **AND** 报告分别披露"过线检出率"与"线内误报率"，不接受单一汇总检出率

#### Scenario: 语义子集验收新规则

- **GIVEN** 术语一致性校验规则已上线
- **WHEN** 对 semantic_mismatch 子集运行准度测量
- **THEN** 该子集检出率 SHALL ≥ 90% 并在准度报告中单独成行

### Requirement: 覆盖率纳入实验指标

run_experiment 的实验报告 SHALL 增加 `citation_coverage` 指标（按 dataset item 聚合均值与 95% CI），与 citation_pass 并列展示；覆盖率变化的显著性判断沿用配对 bootstrap 契约。

#### Scenario: 实验报告含覆盖率

- **WHEN** 对比两个 prompt 版本的实验结果
- **THEN** 报告 SHALL 含 citation_coverage 的均值差与 CI，CI 含 0 时表述为"无显著差异"

### Requirement: judge rubric 扩展语义核对

decision_grounding judge 的 rubric SHALL 扩展：核对 interpretation/报告表述中的指标术语、期次、方向与所引用数值的语义一致性（如数值下降却表述"改善"）。rubric 变更 SHALL 递增版本号，并按 Judge 校准门禁契约重新校准（与人工一致性 ≥80%）后方可上线。

#### Scenario: 解读失当被扣分

- **GIVEN** 报告将行业垫底的 45.2% 毛利率表述为"行业领先"，且 evidence_refs 指向该值
- **WHEN** 运行 decision_grounding judge
- **THEN** judge SHALL 按 rubric 对解读失当扣分（不得仅因数值有出处给高分）
