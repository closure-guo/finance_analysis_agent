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

## 遗留待人工/待资源（2026-09-13 更新）

> 前版「已实施」8 条 delta 全部归档；四类实时验证（FM 回路/数据排序/harden/langfuse-trace）
> 已随 ehr-style/surgical 同步归档；prompt direction 纪律已发布。以下为当前真实遗留。

1. ~~judge 人工校准标注~~ **已闭合（2026-09-13）**：round7 盲标 41 对 + owner 终裁达标（整体
   MAE 0.342 / 方向一致率 97.6%），rubric v7 定稿；round8 基线重建轮经维护者代裁审计无虚高
   （见 docs/evals/2026-09-13-round8-维护者代裁报告.md）。spec 的人工 ≥80% 一致性校验以
   round7 结果为准判定通过。
2. **nightly @live 门禁**（已决策 2026-09-08：不暴露本地 Langfuse、不上云）：
   CI secrets **不配置**，GitHub Actions 侧 @live 维持跳过。live 验证走本地手动
   （`uv run pytest -m live`），或未来愿开电脑时挂 Windows 计划任务在收盘后定时跑。
   **2026-09-13 修复**：@live 用例硬编码 DeepSeek 直连（模型/key/端点）已切方舟生产栈
   （LLM_MODEL/LLM_API_KEY/LLM_BASE_URL，Agent Plan），幻觉率用例同步修 report_chunk
   事件抽取 + data_map source 契约；3 用例本机实测全绿，无 DEEPSEEK_API_KEY 依赖。
3. ~~docker 后端重建~~（2026-09-13 执行）：`docker compose up -d --build` 已刷新，
   FM state 修复/根 span output/session 头/incident 027 修复入镜像。
4. **judge-sample 数据文件入库规矩**：round5-8 盲标/标注样本 xlsx/jsonl 目前未跟踪，
   仅 round1 jsonl 在库——要么统一入库（可审计优先），要么 .gitignore 统一排除（本地
   报告已引用路径），待定。
5. ~~round9 + v8 候选~~ **已闭合（2026-09-14）**：delta `upgrade-judge-material-v8-rubric`
   实施+归档（consistency 补 Trader 方案节、debate 收敛骨架行、rubric v8 两判例）；
   round9 实验 + 审计完成——dg 多来源归属判例达标、Trader→RJ 静默推翻核对首次可判、
   debate 5 分档判例未达标（v9 候选：强制枚举论点标头，已登记 metrics.md 待决策）。
   见 docs/evals/2026-09-14-round9-v8审计.md。
