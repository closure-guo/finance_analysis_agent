# agent-evaluation-suite Specification Delta

## ADDED Requirements

### Requirement: FM 决策分布指标

评估体系 SHALL 统计基金经理节点 approve/modify/reject 分布（`fm_decision_distribution`），并支持与人工抽检的一致率对比。

#### Scenario: 分布统计

- **WHEN** 评测运行且样本含 FM 决策
- **THEN** 报告输出三档决策占比及与人工抽检的一致率

### Requirement: FM 决策分布双向门禁

评测门禁 SHALL 同时约束 approve+modify 占比下限（防「永不批准」）与风控否决召回率下限（防「无脑批准」反向漂移）。

#### Scenario: 永不批准拦截

- **WHEN** approve+modify 占比低于配置下限
- **THEN** 门禁失败并提示 FM prompt 校准异常

#### Scenario: 无脑批准拦截

- **WHEN** 对应当 reject 的对抗样本 FM 未否决的比例超阈值
- **THEN** 门禁失败并提示风控职责失守
