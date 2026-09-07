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

## 遗留待人工/待资源（2026-09-08 更新）

> 前版「已实施」8 条 delta 全部归档；四类实时验证（FM 回路/数据排序/harden/langfuse-trace）
> 已随 ehr-style/surgical 同步归档；prompt direction 纪律已发布。以下为当前真实遗留。

1. **ADR-0018 落地**（tmp/adr-0018-draft.md → docs/adr/）——**人工维护**（agent 不得新建 ADR）；
   其原先解锁的 archive 链（decision-outcome-tracking → expose-decision-outcomes → add-track-record）
   已于 09-05 全部归档，本项仅剩文档落地。
2. **judge 人工校准标注**：首轮跨模型代理门禁已归档（deepseek/qwen/k3 90 对），spec 要求的人工
   ≥80% 一致性校验仍开放——标注工具链就绪（exporter 抽样直链可用），回填 human_score 重跑
   measure.py 即闭合。
3. **nightly @live 门禁 secrets**：CI workflow 已透传 LANGFUSE_*/JUDGE_*，需仓库管理员在
   GitHub Settings 配置 secrets 后 @live 套件（FM 门禁/性能回归/校准抽样）才真正生效。
4. **docker 后端重建**：8000 端口 docker 镜像基于修复前代码（FM state 修复/根 span output/
   session 头等未入镜像）——`docker compose up -d --build` 刷新。
