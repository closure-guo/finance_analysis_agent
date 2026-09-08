# 人工验证报告: add-latency-cost-regression（Task 3.2 收尾）

**日期**: 2026-09-06
**验证人**: ZCode agent（TDD 实现与实测）
**关联 delta**: openspec/changes/add-latency-cost-regression/
**前置**: 1.x/2.x/3.1/4.x 已勾；本报告覆盖最后一项 3.2（nightly 时序归档驱动趋势告警）

## 实现

- `append_history(path, agg, model)`：nightly 每次运行追加聚合记录到 `docs/evals/perf-history.jsonl`（JSONL，含 as_of/model/各指标）
- `load_history_series(path, metric, model)`：读取指标时序，**按模型过滤**（跨模型时延不可比，与基线同原则）
- `run_offline(..., history_path, model)`：趋势由 `detect_trend(归档序列)` 判定，替换原硬编码 False
- `main()`：Langfuse 拉取（nightly 真实流量）时自动归档本轮聚合，再以「归档历史 + 本轮」序列驱动趋势告警；`--traces` 离线模式不归档；`--history`/`--no-archive` 可控

## 验证结果

| 验证项 | 测试 | 结果 | 通过 |
|---|---|---|---|
| 归档写读一致性 | test_append_and_load_history | JSONL 两行、字段完整、序列回读一致 | ✅ |
| 跨模型过滤 | test_load_history_filters_by_model | 按 model 过滤，缺失模型返回空 | ✅ |
| 趋势告警触发 | test_run_offline_history_drives_trend_alert | 历史 1.0→1.1→1.3（+10%/+18% 单调）→ trend_alert True | ✅ |
| 无历史不误报 | test_run_offline_no_history_no_trend | 缺失归档 → False | ✅ |
| 模型不匹配不误报 | test_run_offline_history_model_mismatch_no_trend | 当前模型无序列 → False | ✅ |
| CLI 冒烟 | --traces 离线跑通 | 报告渲染 P50/趋势告警段正常，--no-archive 不写归档 | ✅ |
| 回归 | test_performance.py 全量 | 16/16（原 11 + 新 5） | ✅ |

## 备注

- 归档文件 `docs/evals/perf-history.jsonl` 随 nightly 增长；趋势检测仅需最近 3 轮，文件体量长期无虞
- nightly 工作流（e2e-playwright.yml live job）跑 `evals.run` 后追加执行本模块即自动积累归档
