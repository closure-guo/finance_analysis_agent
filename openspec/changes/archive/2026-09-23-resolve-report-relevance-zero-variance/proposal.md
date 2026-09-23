# Proposal: resolve-report-relevance-zero-variance

## Why

report_relevance 在 r 系列长期零方差/近零方差（r3–r9 deep 段全 5.0 或 4.93，quick 段自 r3 起全 5.0，Spearman 因 judge 全 5 不可计算——metrics.md §1.4/§2 已登记），对回归检测几乎不携带信息；quick 模式下它是唯一 judge 维，且其判据「答非所问」的失败面大部分已被确定性指标（ticker_match / section_coverage）覆盖。hosted 判分切换 K 次均值（`switch-hosted-judge-to-k-mean`）后，quick 条目每维判分成本 ×K 而信息量仍≈0——零方差维度处置从「待决策」升格为应收口的成本与口径问题（metrics.md §3「quick report_relevance 全 5 待 round7 人工口径终裁」挂账项）。

## What Changes

- **quick 条目停评 report_relevance**（**BREAKING**，对内口径）：quick 条目不再产出 judge 分，回归信号由确定性指标（ticker_match / section_coverage / citation 系）承担；`docs/evals/metrics.md` §1.1 口径行更新为 deep-only，时间线登记切点（跨切点 report_relevance 均值不可直接比较）
- **deep 条目保留 report_relevance**（存在 4.86/4.93 的真实方差，「答非所问」在 deep 多焦点查询下仍是真实失败模式）
- deep 的 report_relevance rubric v3 → v4：5 分档收紧锚点判例（query 的显式子问题被逐一回答才可给 5，任一子问题被回避即降 4），`RUBRIC_VERSIONS` 递增
- rubric 变更按「Judge 校准门禁」契约重校准：以 round7 盲标样本离线重判 v4，与人工一致性达标后方可上线
- 「线上托管 Evaluator」需求同步修改：quick 模式不再跑 judge（原契约「quick 仅跑 report_relevance」随之作废）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `evaluation`: ① ADDED「report_relevance 评估范围与 5 分档判例」（quick 停评 + deep rubric v4 锚点）；② MODIFIED「线上托管 Evaluator」（quick 模式从「仅跑 report_relevance」改为不跑 judge）

## Impact

- 代码：`evals/run.py`（quick 条目跳过 judge 判分）、`evals/judges.py`（report_relevance rubric v4 + `RUBRIC_VERSIONS` 递增）；测试同步
- 校准：round7 盲标样本离线重判 report_relevance v4（与人工一致性 ≥80% 达标才上线）
- 台账：`docs/evals/metrics.md` §1.1 口径行（deep-only + v4）+ §2 时间线切点 + §3 划线关闭「quick report_relevance 全 5 待终裁」挂账项
- 成本：每轮 hosted 实验省 quick 条目 judge 调用（9 条 × K 次），与 K 均值切换的 ×K 增量部分对冲
