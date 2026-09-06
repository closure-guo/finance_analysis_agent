# Tasks: add-latency-cost-regression

## 1. 度量采集

- [x] 1.1 失败测试先行：聚合口径与基线对比（tests/evals/test_performance.py，11 例）
- [x] 1.2 Langfuse trace 聚合（延时/latency、token（GENERATION usage 汇总）、成本（PRICE_TABLE 模型单价表配置化）），quick/deep 分开；单条拉取失败不阻断整批

## 2. 基线与门禁

- [x] 2.1 基线档案 docs/evals/perf-baseline.json（--save-baseline 落盘；真实首版基线待 nightly 首次运行生成）
- [x] 2.2 超基线阈值（PERF_REGRESSION_PCT 默认 30%）告警/失败（compare_with_baseline → regressed 标记）

## 3. 趋势

- [x] 3.1 单调劣化趋势检测（detect_trend：连续 3 轮每轮 ≥5%）
- [x] 3.2 nightly 时序归档驱动趋势告警（当前离线路径置 False，归档历史接入后启用）——**待办**（2026-09-06 落地：perf-history.jsonl 时序归档 + 按模型过滤序列 + detect_trend 接线 main；TDD 5 例先红后绿，CLI 冒烟通过；报告 tests/validation/2026-09-06-add-latency-cost-regression-validation.md）

## 4. 验证

- [x] 4.1 uv run pytest（本模块 11 例）/ ruff / mypy 全绿
- [x] 4.2 nightly @live 注册：tests/evals/test_performance_live.py（pytest -m live，无 key 跳过；本机真跑产出 reports/perf-report-20260904.md：300 traces，P50 0.74s）
