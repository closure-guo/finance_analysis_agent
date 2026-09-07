# Tasks: surgical-citation-repair

## 1. 单点修复模块（TDD：先写失败测试）

- [x] 1.1 失败测试：`citation_repair.build_repair_prompt`（出错句 + 前后各一段上下文 + ground_truth + 申报格式示例 + 只改必要处指令）
- [x] 1.2 失败测试：`citation_repair.locate_sentence`（按 claim 关联数字定位出错句；多命中取首个并告警）
- [x] 1.3 失败测试：`citation_repair.apply_repair`（整句替换回填；找不到原句时返回失败不盲写）
- [x] 1.4 实现 `src/finance_agent/nodes/citation_repair.py` 三个纯函数 + 一次 LLM 调用封装（llm_config 端点、低 temperature、usage 上报）

## 2. 校验节点分流与重校验

- [x] 2.1 失败测试：单分析师单轮 value_mismatch <3 → 走单点修复、不触发分析师重试派发
- [x] 2.2 失败测试：value_mismatch ≥3 → 回退现有定向重试路径、零修复调用
- [x] 2.3 失败测试：回填后强制整体重跑 verify_citations，新错照常分桶暴露
- [x] 2.4 失败测试：重校验后同处仍 FAIL → 不二次单点修复，回退全量重试或按既有放行
- [x] 2.5 失败测试：停滞降级（curr ≥ prev×80%）对单点修复轮同样生效
- [x] 2.6 实现 citation_node.py 分流 + 重校验 + iteration_count 共享

## 3. 遥测与预算

- [x] 3.1 失败测试：value_mismatch_repaired 遥测 + 原 value_mismatch 桶计数保留（trace metadata：修前句/修后句/真值/重校验结果）
- [x] 3.2 失败测试：修复 LLM 调用计入预算记账（usage/token 上报口径与分析师调用一致）
- [x] 3.3 实现埋点（`_report_to_langfuse` 同款模式）

## 4. 验证与归档前置

- [x] 4.1 全量后端测试 2033 passed + ruff/mypy（改动文件 0 错误）通过
- [x] 4.2 全链路验证（2026-09-07）：tests/nodes/test_citation_node.py::TestSurgicalRepair + TestSurgicalRepairIntegration（真实 repair_claims+mock LLM 契约：修复调用→回填→重校验 PASS→value_mismatch_repaired 遥测）+ 稀疏<3 走单点/≥3 回退/崩溃回退/停滞透传 5 例；报告 tests/validation/2026-09-07-ehr-surgical-validation.md
- [x] 4.3 bucket 脚本增 surgical_repair 口径（value_mismatch_repaired + surgical_repairs 明细）并复跑存量：FAIL 分布 value_mismatch 17 条、D6 残留 0，无回归（reports/citation-bucket-analysis-20260907.json）
- [x] 4.4 本批与 ehr-style-claim-direction 同时归档（前置满足）
