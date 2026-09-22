# Tasks: switch-hosted-judge-to-k-mean

- [x] `docs/evals/metrics.md` §1.1 口径先行更新：judge 维度点估计 = K 次均值（默认 3、不用中位、离散度落盘），并在 §3 划线关闭「hosted 实验路径仍是单次判分」待决策项
- [x] 失败测试先行：`evals/run.py` hosted 判分走 `run_judge_mean`（含 `--judge-repeats` 透传、K 写入产物 config、默认 3）
- [x] item 记录塑形：`scores` / `score_spread` 落盘；部分失败不计均值但计 `judge_failures`、全失败 `score=None`；debate 遥测取最低分调用
- [x] 非 debate 维度结果形状回归（不新增 debate 专有键）既有精确断言测试通过
- [x] `docs/evals/metrics.md` §2 时间线登记「单次判分 → K 均值」切点行（跨切点绝对分不可直接比较）
- [x] 全量测试通过（`uv run pytest`：3118 passed / 2 skipped，2026-09-22）
- [ ] 首轮 K 均值口径 hosted 实验收口时：runs.jsonl 追加行带切点标注（留待真实跑批，非本变更代码范畴）
