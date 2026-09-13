# Tasks: add-judge-human-calibration

## 1. 标注工具

- [x] 1.1 失败测试先行：导出表结构与一致性计算（tests/evals/test_judge_calibration.py 8 例）
- [x] 1.2 抽样导出 CLI（tests/scripts/judge_calibration_export.py：Langfuse 抽样 × 4 维度，
       judge 分自动提取、human_score 置空待标注，JSONL 落盘）
- [x] 1.3 标注表格式 + 仲裁流程说明（measure.py docstring；每轮 ≥30 条建议见 delta proposal）

## 2. 一致性指标

- [x] 2.1 Spearman（纯 Python 秩相关）/ MAE / 方向一致率计算
- [x] 2.2 校准报告生成（按维度 + 整体，reports/judge-calibration-report.md）

## 3. 校准回路

- [x] 3.1 阈值配置化（JUDGE_MIN_SPEARMAN/JUDGE_MAX_MAE/JUDGE_MIN_DIRECTION）+ 低于阈值
       need_calibrate 标注 → 触发 judge prompt 修订流程（走 prompt-deploy 管线后重测）
- [x] 3.2 judge prompt 变更后强制校准（流程性约定：变更后必跑 measure.py；结论归档 docs/evals/）
- [x] 3.3 首轮真实标注 + 校准报告——**已闭合（2026-09-14）**：round7 盲标 41 对 + owner 终裁达标
       （整体 MAE 0.342 / 方向一致率 97.6%，judge 自 round7 起可用；round8 维护者代裁审计无虚高），
       报告 docs/evals/2026-09-13-round7-judge校准报告.md；后续 rubric v7→v5 各维度按版本重校准纪律执行中

## 4. 验证

- [x] 4.1 uv run pytest / ruff / mypy 全绿

## 归档注记（2026-09-14）

本 delta 的 spec 内容已在此前 agent-evaluation-suite 主规范的归档同步中先行落库（9 条 requirement/scenario 比对：主规范为超集，零缺失），故本次归档使用 --skip-specs，无内容丢失。
