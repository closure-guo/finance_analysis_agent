# Proposal: surgical-citation-repair

## Why

现行 value_mismatch 重试让目标分析师整份报告重跑（几十次 LLM 调用、分钟级），但失败往往是稀疏单点（incident 022：1/46=2.2%）； FinGround（arXiv 2604.23588）实证单点有据改写是低成本修复路径（净改善 +71.3%），同时实证修复自身有 ~4.1% 错误引入率且随修复处数复利（≥3 处错误率飙至 14.3%）——单点修复必须配套强制重校验与转全量阈值。带真值的叙事改写是唯一能把正确答案缝进报告的方式（确定性替换会留下自相矛盾叙事或洗白错误），本 delta 把它的范围从"整份报告"收缩到"出错句"。

## What Changes

- value_mismatch 定向重试新增**单点修复路径**：将出错句（含所在章节局部上下文）+ ground_truth + direction/申报示例喂给一次轻量 LLM 调用，改写后回填正文再重校验；不再重跑目标分析师
- **复利防护阈值**（FinGround 实证）：单分析师单轮 value_mismatch ≥ 3 处 → 放弃单点修复，回退现有全量定向重试路径
- **修复后强制重校验**：回填正文后重跑完整 citation 校验（值容差 + 术语/期次 + coverage 普查）；残留错误照常暴露（修复不吞错）
- **修复留痕**：repair 调用与结果进 Langfuse trace（修前句/修后句/真值/新错检出）；修复保留原 value_mismatch 分桶计数（`value_mismatch_repaired`），prompt 优化的归因信号不被吞
- 修复调用计入管线 LLM 预算记账（llm-budget-governance 口径）
- 现有停滞降级（fail_rates ≥ 80%）、轮数上限 3、轻微失败直判放行语义全部不变

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `citation-retry-policy`: value_mismatch 重试前置单点修复分支（阈值分流 + 回退全量）；修复调用预算记账
- `citation-verification`: 修复回填后的强制重校验要求；`value_mismatch_repaired` 遥测口径

## Impact

- 影响文件：`src/finance_agent/nodes/citation_node.py`（修复分支 + 回填 + 重校验）、`src/finance_agent/routing.py`（不动路由函数，分流在校验节点内完成）、新模块 `src/finance_agent/nodes/citation_repair.py`（单点改写 prompt + 调用）
- 依赖：方向 delta（ehr-style-claim-direction）的 repaired 留痕模式先落或同批落地，避免两套修复遥测口径
- E2E 门禁：不适用（无前端 UI/SSE/会话状态变更）
- 评估影响：分桶脚本需增 `value_mismatch_repaired` 口径；citation_pass 语义不变（修复后全过即 PASS）
