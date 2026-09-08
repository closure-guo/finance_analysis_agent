# 人工验证报告：surgical-citation-repair

**日期**：2026-09-05
**验证人**：agent（ZCode）+ 用户委托自动化验证
**delta**：openspec/changes/surgical-citation-repair（value_mismatch 稀疏失败的单点有据改写）

## 验证环境与方法

- 后端单测：`uv run pytest`（非 live 全量）
- Lint/类型：`uv run ruff check`（全绿）/ `uv run mypy`（改动文件零新增）
- 管线冒烟：TESTING stub 直驱图（前置 delta 已验证，本 delta 无管线级分支差异——修复仅在 stub 产出的 claim 出现 value_mismatch 时触发，stub 管线为干净路径）

## 验证结果

### 1. 分流语义（TDD 红→绿）

| 场景 | 期望 | 实际 |
|---|---|---|
| 稀疏失败（1 处 value_mismatch）→ 单点修复 | 修复调用 1 次；重校验 PASS；无重试目标 | ✅ 一致 |
| 密集失败（4 处）→ 回退全量定向重试 | 修复调用 0 次；retry_targets=["fundamental"] | ✅ 一致 |
| 修复后重校验仍 FAIL（同处） | 不二次单点修复（调用数=1）；回退 retry_targets | ✅ 一致 |
| 修复模块崩溃 | 校验不受阻，走既有重试路径 | ✅ 一致 |
| 停滞降级（fail_rates 35%→31%）+ 修复适用 | 仍按停滞 render；fail_rates 序列透传 | ✅ 一致 |

### 2. 修复不吞错（citation-verification delta 要求）

- 修复成功的 claim 由 LLM 申报新 stated_value 并以 model_copy 重建（interpretation=修复后整句）→ **重校验是仲裁**：LLM 改错（stated 与真值超容差）照常 value_mismatch FAIL 并回退全量重试（test_repaired_still_failing 实证）
- 修复模块输出无契约（缺 repaired_sentence/stated_value）→ repaired=False，正文不动
- 整句替换找不到原句 → None 不盲写

### 3. 遥测与预算

- `citation_fail_buckets` 原桶保留（value_mismatch 计数不因修复抹除，max 合并新错）
- 输出新增 `citation_repairs`（before/after/ground_truth/repaired/updated_claim）与 `value_mismatch_repaired` 计数
- Langfuse span metadata 携带 citation_repairs（遥测失败不阻断）
- 修复 LLM 调用经 `call_llm_for_json`（node_name="citation_repair"）→ 与分析师同口径的 gateway usage 记账；llm_config 透传有测试锁定

### 4. 全量回归

- `uv run pytest`：**1986 passed, 2 skipped**；7 个 @live 用例环境性跳过（ark 余额为零，同前置 delta 报告，非回归）
- ruff 全绿；mypy 改动文件（citation_node/citation_repair）零新增错误

## 已知限制

- 修复质量（LLM 改写引入新错率）依赖真实 LLM 行为，单元层以 mock 验证流程与安全护栏；FinGround 实证引入率 ~4.1% 且有重校验兜底——真实产出下的 repaired→PASS 转化率待 LLM 余额恢复后由 `citation_bucket_analysis.py` 增补口径复测
- locate_sentence 为启发式（句内数值 ≈ stated_value），定位失败时该处跳过（repaired=False），不误改

## 结论

全部规格场景有测试实证；满足 archive 前置：tasks 全勾 + verification 通过 + 本报告落 tests/validation/。非交互类变更，E2E 门禁不适用。
