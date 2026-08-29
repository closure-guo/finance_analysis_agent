# 验证报告: fix-citation-contract-diseases

**日期**: 2026-08-29
**验证人**: ZCode agent（自动化验证；人工抽查项见文末）
**关联 delta**: openspec/changes/fix-citation-contract-diseases/
**关联 incident**: docs/incidents/020-citation-contract-diseases-20260828.md
**E2E 门禁**: 不适用（非交互类变更）

## 自动化门禁

| 门禁 | 结果 |
|---|---|
| `uv run pytest -m "not live" -q` | **1411 passed / 2 skipped / 8 deselected**（main 基线 1381 + 本 delta 30） |
| `uv run ruff check`（delta 文件） | 全绿 |
| `uv run mypy`（citation.py + analysts.py） | 0 错误（TypeGuard 收窄） |
| 离线重判（002412 round-2 67 claims fixture） | **41 FAIL → 5**，残量全部为真幻觉（序列全量搜索证伪，引用集合钉死） |
| prompt 发布 | `deploy_prompts.py` 14 OK（四分析师示例对齐后） |

## 真实端到端验证（决定性证据）

**2026-08-29，汉森制药 002412 真实深研全管线跑批**（修复后代码 + 新 prompt，GLM-5.3，直连 graph.invoke）：

| 指标 | 修复前（2026-08-26 复盘） | 修复后（本次实跑） |
|---|---|---|
| claims 总数 | 67 | 28 |
| FAIL | **41（61%）** | **0** |
| PASS | 15 | 25 |
| UNVERIFIABLE | 15 | 3（coverage_gaps=0 → 全为 llm_inference 契约跳过，非缺口） |
| citation_pass | false（触发分析师全量重跑） | **true（iteration_count=1，零重试）** |
| 管线耗时 | 分析师每轮 12~16 分钟 × 重试 | **全程 2.7 分钟** |

原始 JSON 证据：`reports/citation_live_verify_002412.json`（运行产物，不入库；本表为摘录）。

## 契约对照

- 修 A：`technical_indicators.MA.5.-1` 等负索引引用在真实运行中被 LLM 采用并校验 PASS（tests/test_citation_contract.py::TestNegativeIndex）
- 修 B：真实 context 段落标题带英文键标注；DataFrame 行键.列名 / `[N]` 括号 / 中文根键不静默映射均有单测
- 修 C：亿元级容差与双条件 FAIL 语义单测锁定

## 人工抽查项（可选）

- [ ] Langfuse UI 抽查本次 trace 的 citation span 明细与 claims 数值
- [ ] 换 1-2 只其他标的重复深研，确认 FAIL=0 可复现（不同数据形态下）

## 结论

全部通过。契约疾病（假 FAIL）归零且有回归网钉死；真实管线 citation_pass 首轮通过。
