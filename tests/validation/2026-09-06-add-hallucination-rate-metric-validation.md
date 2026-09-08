# 人工验证报告: add-hallucination-rate-metric（Task 3.2 / 4.2 收尾）

**日期**: 2026-09-06
**验证人**: ZCode agent（TDD 实现与实测）
**关联 delta**: openspec/changes/add-hallucination-rate-metric/
**前置**: 1.x/2.x/3.1/4.1 已勾；本报告覆盖最后两项 3.2（门禁阈值接入报表）与 4.2（事实型 claim LLM 抽取）

## 验证结果

| 验证项 | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|
| 3.2 门禁阈值 | 幻觉率上限可配（HALLUCINATION_MAX_RATE），报告含门禁判定段 | 宽松初值 **10%**；render_report 新增「门禁判定」段（阈值 + pass/fail/insufficient_sample） | ✅ |
| 小样本防误报 | 可验证样本 < GATE_MIN_N（默认 5）不判定 | insufficient_sample 语义（rate=None 或样本不足均不误判） | ✅ |
| CI 语义 | 门禁可阻断 | measure.py main 对 fail 返回非零 exit code 语义（gate verdict 判定函数纯函数可测） | ✅ |
| 4.2 事实型抽取 | LLM 抽取事实型断言并入结果 | extract_factual_claims（llm.invoke 约定，同 evals judges）：无 LLM/坏 JSON 优雅回退空；抽取结果并入 run_offline，无证据源时如实 unverifiable 不进分子 | ✅ |
| 测试 | 先红后绿 | test_hallucination.py 18/18（原 9 + 新 9：门禁 5 + 抽取 4） | ✅ |

## 配置说明

- `HALLUCINATION_MAX_RATE`：门禁上限，默认 0.10（宽松初值，随基线积累收紧）
- `HALLUCINATION_GATE_MIN_N`：最小可验证样本数，默认 5
- 事实型抽取需调用方注入 llm 客户端（`run_offline(..., llm=...)`），离线路径不注入时仅数值型核验——与「需 LLM 余额」的成本边界一致

## 结论

- [x] 3.2 / 4.2 通过，可 archive（任务 8/8）
