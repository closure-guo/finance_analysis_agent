# 人工验证报告：ehr-style-claim-direction

**日期**：2026-09-05
**验证人**：agent（ZCode）+ 用户委托自动化验证
**delta**：openspec/changes/ehr-style-claim-direction（EHR 式 claim 五元组：direction 独立申报）

## 验证环境与方法

- 后端单测：`uv run pytest`（非 live 全量）
- Lint/类型：`uv run ruff check` / `uv run mypy`（对比改动前基线）
- Prompt 发布：`uv run python scripts/deploy_prompts.py`（Langfuse 14/14 OK）
- 管线冒烟：TESTING=1 + STUB_SCENARIO=pipeline 直驱 `build_5layer_graph()`

## 验证结果

### 1. 方向判定语义（单元级，TDD 红→绿）

| 场景 | 输入 | 期望 | 实际 |
|---|---|---|---|
| 负向修饰匹配 | stated=10.05, direction=negative, gt=-10.05 | PASS | ✅ PASS |
| 方向申报冲突 | stated=10.05, direction=positive, gt=-10.05 | FAIL + direction_mismatch 桶 | ✅ 一致 |
| 旧格式降级（值级 FAIL） | direction=None | FAIL value_mismatch + coverage_gap | ✅ 一致 |
| 旧格式降级（值级 PASS） | direction=None, stated=-10.05 | PASS + coverage_gap（显式降级不静默） | ✅ 一致 |
| flat 跳过符号检查 | direction=flat, stated=gt | PASS 无缺口 | ✅ 一致 |
| 双路径二义消除 | 已申报 direction + 正文含冲突方向词 | 不走词表核对 → PASS | ✅ 一致 |
| 词表兜底补词 | 负增长/跌幅/收窄 语境 | direction_neg=True、符号不敏感认领 | ✅ 一致（34/34） |
| 重试反馈 | direction_mismatch | 携带真值符号 + direction 申报示例 | ✅ 一致（36/36） |
| 打回提示 | coverage_gap 条目 | 携带 direction 补申报提示 | ✅ 一致 |
| pydantic 拒绝 | direction="down" | ValidationError | ✅ 一致 |

### 2. 契约测试与 prompt 发布

- prompt 契约测试（含新增 TestClaimDirectionDiscipline 8 用例）：54/54 通过
- deploy_prompts.py：14 个 prompt 全部发布成功（Langfuse health 200）

### 3. 全量回归

- `uv run pytest`：**1968 passed, 2 skipped**；7 个 deselected 为 @live 测试（test_eval_live / outcome_live / trace_content_live / ark contract probe）——需真实 LLM 余额，当前 ark 余额为零，属环境性不可用，非本 delta 回归（涉及文件本次零改动，git status 证实）
- `uv run ruff check`：All checks passed
- `uv run mypy`：src 71 errors 与改动前基线**完全一致**（零新增）；测试文件净 -3（收编存量 dict-unpack 错误）

### 4. 管线冒烟（TESTING stub）

- 五层图端到端跑通：citation_pass=True、coverage=1.0、无桶、无崩溃——新 schema 未破坏管线
- **已知限制**：stub LLM 产出的 claim 不携带 direction（全部走旧格式降级路径，计覆盖缺口但不 FAIL），故 direction_mismatch 桶的端到端 trace 验证需待真实 LLM 余额恢复后，用 `tests/scripts/citation_bucket_analysis.py` 复跑确认新桶遥测出现（该口径已在脚本支持范围）

## 结论

行为验证全部通过；7 个 live 用例因 LLM 余额为零环境性跳过（已在上方列明，非回归）。
本 delta 满足 archive 前置：tasks 全勾 + verification 通过 + 人工验证报告（本文）落 tests/validation/。
非交互类变更（无 UI/SSE/会话状态变更），E2E 门禁不适用。
