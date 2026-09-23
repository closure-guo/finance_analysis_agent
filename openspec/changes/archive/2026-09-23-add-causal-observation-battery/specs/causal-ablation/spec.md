# Delta for Causal-ablation

## ADDED Requirements

### Requirement: 常规观测电池

系统 SHALL 提供常规观测电池驱动：对**固定材料快照**（P1 快照 20 标的，digest 核验与跑批登记值一致）以当前生产栈（prompt / 模型）跑材料腿，产出三个已校准读数——grounding 无源断言率、B1 风险点吸收率、B2 交锋修正率——一键执行。判定实现 SHALL 复用因果消融库侧函数（`bear_grounding` / 族 B 判定），SHALL NOT 另行实现判定逻辑。观测轮 SHALL 不作层增量裁决：无两臂对照时 SHALL NOT 产出层间结论句，读数定位为跨轮趋势观测（与上轮对照、人工解读）。校准门控 SHALL 沿用：三读数对应的 nli/judge rubric 变更后未重过 0.80 校准门的，该读数 SHALL 标 `provisional` 且 SHALL NOT 与历史轮直接对照。每轮观测 SHALL 落 `runs.jsonl`（含材料腿与判定腿调用数）并登记 `docs/evals/metrics.md` 时间线；触发约定为生产 prompt / 模型栈变更后运行。

#### Scenario: 一键跑观测电池

- **WHEN** 以观测电池入口对固定快照 × 当前生产栈执行
- **THEN** SHALL 产出 grounding 无源率 / B1 吸收率 / B2 修正率三读数（含分母行数与解析失败数）
- **AND** runs.jsonl SHALL 追加一行（含 llm_calls 分材料腿/判定腿申报）

#### Scenario: 固定快照跨轮可比

- **GIVEN** 观测电池上一轮登记的快照 digest
- **WHEN** 本轮观测启动并重建材料快照
- **THEN** digest 与登记值不一致时 SHALL 显式失败（输出标的与两侧 digest），SHALL NOT 静默混轮比较

#### Scenario: 观测轮不作层增量

- **WHEN** 汇总观测电池读数
- **THEN** SHALL 只呈现三读数的跨轮对照与趋势解读
- **AND** SHALL NOT 出现任何层增量结论句（无两臂对照，层归因须走因果消融实验批）

#### Scenario: 校准门控沿用

- **GIVEN** B1 吸收判定的 rubric 自上轮观测后发生变更且未重过 0.80 校准门
- **WHEN** 本轮观测产出 B1 读数
- **THEN** 该读数 SHALL 标 `provisional`，SHALL NOT 与历史轮直接对照

#### Scenario: 变更触发

- **WHEN** 生产 prompt 发布（`deploy_prompts.py`）或模型栈切换完成
- **THEN** 观测电池 SHALL 可被触发执行，读数登记于 metrics.md 时间线（对应变更的 HEAD@启动）
