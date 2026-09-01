# Proposal: harden-citation-semantic-coverage

## Why

契约修复（负索引/英文键/相对容差）与 L1 准度基线落地后，引用校验的"指针工程正确性"已趋完备，但对照文献最佳实践（ALCE 的 Citation Recall、ProvenanceBench 分层校验、归因 vs 引用二维划分）与冒烟验证新发现，仍有四类未覆盖的系统性缺口：

1. **逃逸口未堵**：校验是"LLM 自报制"——正文 markdown 中未申报为 claim 的数字完全不受校验（`citation_pass=100%` 也可以满篇黑数字），对应 ALCE Citation Recall 维度，文献共识是"未引用断言计 0"，本系统无等价机制；
2. **语义层未覆盖**：数值抄对但术语/期次张冠李戴（毛利率写成净利率、年报值说成季报值）结构性逃逸——校验只比 field_ref + stated_value，不看 interpretation；
3. **context 语义未声明**：冒烟验证（中际旭创 13 条 FAIL）实证 LLM 按行情软件习惯误读 K 线数组方向，编造期次错位叙事——context 未声明数组内部顺序，与 `data-ordering-citation-contract` 同族；
4. **重试路由粗放**：任一 FAIL 触发分析师全量重跑，实测占管线耗时 28-29% 且三轮重试失败率停滞（35%→38%→31%），属纯成本。

参考：ALCE（Gao et al. 2023）、ProvenanceBench、FinGround（arXiv:2604.23588）、incident 022。

## What Changes

1. **`citation-verification` 扩展六条契约**：
   - context 数据形态语义声明（数组方向/负索引/期间标签，LLM 所见即校验语义）；
   - Claim schema 扩展 `metric_name`（枚举）+ `period`，术语/期次与 field_ref 一致性确定性校验；
   - claim 内部一致性校验（stated_value 在 interpretation 中可匹配 + 方向词与 delta 符号核对）；
   - 正文覆盖率校验（markdown 数字普查，产出 `citation_coverage` Score）；
   - 校验失败按桶分流 + 定向重试（值级 FAIL 只重跑关联分析师；格式类 FAIL 直判不触发重试）；
2. **`evaluation` 扩展**：基准集 v1.1（near_miss 改容差边界档 ±{0.3,0.5,0.7,1}% 并含 should_pass 样本；新增 semantic_mismatch 对抗子集）；`citation_coverage` 纳入实验指标；`decision_grounding` judge rubric 扩展 interpretation 语义核对。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `citation-verification`：新增 context 语义声明、术语/期次一致性、内部一致性、覆盖率、失败分流五类要求。既有容差语义（绝对 0.01 / 相对 0.5%）与三态裁决不变。
- `evaluation`：新增基准集 v1.1 构造规则、覆盖率指标、judge rubric 扩展要求。既有实验工作流与显著性契约不变。

## Impact

- **代码**：`models.py`（Claim 扩字段）、`citation.py`（三条新确定性检查 + 分流）、`nodes/analysts.py`（context 构建声明语义）、`routing.py`（重试路由）、`nodes/citation_node.py`（覆盖率 Score）、prompts（分析师/claim 申报约束）、`evals/claim_benchmark/`（v1.1 生成器）。
- **Langfuse**：新增 Score `citation_coverage`（NUMERIC 0-1）；judge rubric 版本迭代。
- **协调**：依赖契约修复已合入（负索引/词表统一是术语一致性检查的前提）；与 `agent-evaluation-suite` 的 run_experiment 通过指标扩展衔接；修复后需重跑 measure.py 刷新 verifier 基线为 v1.1。
- **架构决策**：重试路由变更属行为变更，**建议人工落一条 ADR**；Claim schema 变更影响 AnalystReport 解析兼容（旧报告 claims 缺新字段，需 default 兼容）。
- **风险**：中 —— 数字普查的正则归一化存在口径风险（"45.2%"vs"45.2"vs"约45%"），需 fixture 测试钉死；覆盖率目标不设 100%（比例、评级类表述允许豁免），阈值需人工确认；定向重试减少重跑次数，可能暴露原本被全量重跑掩盖的分析师间状态依赖。
