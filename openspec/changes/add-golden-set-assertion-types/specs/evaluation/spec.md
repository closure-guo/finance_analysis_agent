# Delta for evaluation

## MODIFIED Requirements

### Requirement: 校验器准度测量与门禁

系统 SHALL 提供校验器准度测量。整体 F1 ≥ 0.90 与相对冻结基线退步 ≤ 0.02 的 CI 门禁 SHALL 保留，但门禁产物（measure 报告）SHALL 显式披露所用基准集的身份：`rule_derived`（构造标签）基准集 SHALL 被标注为「算法回归探针——仅验证实现未回归，不构成真实准度声明」；真实准度声明 SHALL 仅来自含人工标注（annotator=double_human/single_human）与真实来源（origin 非空）的金标准集，且须报告标注者一致性 κ。两个信号 SHALL 分开展示，SHALL NOT 混编为一句话的「F1 可信」。

(Previously: 校验器 F1 ≥ 0.90 即为「准度可信」，未区分基准集身份与来源。)

#### Scenario: 构造集身份披露

- **WHEN** CI 或报告中呈现校验器 F1
- **THEN** 若基准集全部为构造标签，SHALL 输出「回归探针，非真实准度」声明
- **AND** SHALL NOT 出现「校验器准度可信」措辞

#### Scenario: 真实准度声明

- **WHEN** 使用含人工标注与真实来源的样本报告准度
- **THEN** SHALL 报告整体 P/R/F1（带 CI）与标注者一致性 κ
- **AND** F1 ≥ 0.90 时方可表述「准度可信」