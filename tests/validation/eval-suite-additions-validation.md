# 评估补强五项 验证报告

- 日期：2026-09-04
- 提交：a038970（add-latency-cost-regression）、3f429ad（add-toolcall-evaluation）、
  269c841（add-hallucination-rate-metric v1）、52a6451（add-judge-human-calibration +
  enable-hosted-evaluator 降级）

## 各项自动化验证

### add-latency-cost-regression（a038970）
- tests/evals/test_performance.py 11 例：usage 汇总/成本估算（单价表）/分位聚合/
  基线回归阈值（PERF_REGRESSION_PCT 30%）/趋势检测（连续 3 轮单调劣化）
- @live 真跑：300 traces（quick 286/deep 14），P50 0.74s/P90 7.4s；无 usage 时
  token/成本如实「—」；报告 reports/perf-report-20260904.md

### add-toolcall-evaluation（3f429ad）
- 取证：工具执行未入 Langfuse → 配套埋点 _trace_tool（6 处注册，sync/async
  双路，零开销直通，6 例守卫测试）
- 回归修复：is_streaming 经 __wrapped__ 穿透包装器（裸判定把包裹后的流式工具
  误判为普通工具 → THINK 丢弃；全套曾现 6 失败，修复后归零）
- tests/evals/test_toolcall.py 15 例：提取/合法集合/参数/效率/失败恢复 + 金标
  零违例 + 对抗样本全检出；@live 监控报告可生成

### add-hallucination-rate-metric v1（269c841）
- 范围决策：v1 仅数值型 claim（规则抽取 + 行情/财务校验，无 LLM）；事实型
  claim 抽取需 LLM 标后续
- tests/evals/test_hallucination.py 9 例：抽取/容差判定（价±2%、涨跌±0.5pp、
  市值±10% 等）/幻觉率口径（unverifiable 不进分子）
- @live 真跑：真实报告 10 claims；行情源缺失 → 全部 unverifiable 如实报告
  （reports/hallucination-report-20260904.md）

### add-judge-human-calibration（52a6451）
- tests/evals/test_judge_calibration.py 8 例：导出（trace.scores/judge 观测）、
  Spearman（纯 Python 秩相关）/MAE/方向一致率、阈值 need_calibrate
- 标注 CLI：tests/scripts/judge_calibration_export.py（只读 API，JSONL 落盘）
- 维度对齐真实口径（run.py _JUDGE_DIMS 四维）

### enable-hosted-evaluator（52a6451，降级方案）
- 取证：自托管 Langfuse 3.205.1 无 evaluator 公共 API → 降级轮询
  /api/public/scores
- tests/evals/test_hosted_evals.py 6 例：窗口聚合/阈值告警/口径对齐 MAE
- 模板治理：docs/evals/hosted-evaluator-template.md 快照归档（UI 配置后回填）

## 汇总

- 全套后端 pytest：1912 passed / 0 failed
- ruff / mypy 全绿；四个 delta 均过 openspec validate --strict

## 待人工验证

1. judge 首轮人工标注（≥30 条）→ measure.py 出首份校准报告（人力活）
2. hosted evaluator UI 配置 + 模板回填 + 真实流量监控（需 LLM 余额）
3. 性能基线首版落盘（nightly 首跑 --save-baseline）+ 趋势归档接入
