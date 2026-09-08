# Backlog 索引

> 状态（2026-09-04 晚）：立项的 8 条 delta 已全部实施完毕（提交 225b10d / 12af347 /
> 417fd28 / ee1159c / a038970 / 3f429ad / 269c841 / 52a6451）。各 delta 的待办仅剩
> 人工环节或需 LLM 余额的验证项，明细见各 delta tasks.md 与 tests/validation/ 报告。

## 已实施

| Delta | 内容 | 验证报告 |
|---|---|---|
| calibrate-fm-approval | 取证证伪「FM 永不批准」+ return 回路反馈修复 + FM 决策双向门禁 | tests/validation/calibrate-fm-approval-validation.md |
| add-track-record-stage-b | 盯市/净值/风险收益指标 + 战绩页风险卡与净值图 | tests/validation/track-record-stage-b-validation.md |
| add-track-record-stage-c | 校准页/四维切片/详情页/版本分段（P6）/完整性校验 | tests/validation/track-record-stage-c-validation.md |
| add-toolcall-evaluation | 工具调用埋点（_trace_tool）+ 四维评估 + is_streaming 回归修复 | tests/validation/eval-suite-additions-validation.md |
| add-hallucination-rate-metric | v1 数值型 claim 抽取 + 证据校验 + 幻觉率门禁 | 同上 |
| add-latency-cost-regression | 时延/token/成本聚合 + 基线回归门禁 + 趋势检测 | 同上 |
| add-judge-human-calibration | 标注导出 CLI + Spearman/MAE/方向一致率 + 校准触发 | 同上 |
| enable-hosted-evaluator | 降级方案：scores 轮询 + 告警 + 口径对齐 + 模板快照 | 同上 |

## 遗留待人工/待资源

1. **ADR-0018 落地**（tmp/adr-0018-draft.md → docs/adr/）→ 解锁 archive 链：
   decision-outcome-tracking → expose-decision-outcomes → add-track-record
2. LLM 余额恢复后：FM return 回路真实验证（tasks 4.3）、judge 首轮人工标注、
   hosted evaluator UI 配置、幻觉率事实型 claim（LLM 抽取）
3. 下个交易日收盘后：真实行情盯市/净值确认（stage-b tasks 4.3）
