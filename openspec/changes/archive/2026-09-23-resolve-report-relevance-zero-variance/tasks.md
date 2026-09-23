# Tasks: resolve-report-relevance-zero-variance

- [x] `docs/evals/metrics.md` §1.1 口径先行更新（report_relevance 转为 deep-only + rubric v4 判例）
- [x] 失败测试先行：run_experiment 对 mode=quick 条目不发起 judge 调用、不产出 report_relevance 分数（确定性指标照常）
- [x] rubric v4 判例落地（5 分档锚点：显式子问题逐一回答）+ `RUBRIC_VERSIONS` report_relevance 递增为 4；版本钉死测试同步
- [x] 校准对照：round7 盲标样本（v2 xlsx，14 行 relevance）离线重判 v4（K=3 均值，脚本 `tests/scripts/rejudge_relevance_v4.py`）——MAE 0.143 / 方向一致率 1.000，过门（≤1.0 / ≥0.80）；产物 `evals/judge_calibration/data/judge-sample-round12-relevance-v4.jsonl`
- [x] 契约抽验如实记录：本样本 14 行 v4 全部仍 5（含人工打 4 的两行），锚点判例未产生降分行——判例实际区分力待多焦点查询样本验证（已写入 metrics.md 切点行，非静默放行）
- [x] `docs/evals/metrics.md` §2 时间线登记切点行（deep-only + v4，跨切点均值不可直接比较）
- [x] 全量测试通过（`uv run pytest`）
