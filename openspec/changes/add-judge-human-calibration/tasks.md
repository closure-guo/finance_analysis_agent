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
- [ ] 3.3 首轮真实标注 + 校准报告——**待人工**：跑 export CLI → 人工打分 ≥30 条 →
       measure.py 出报告（需人工标注资源，无法自动化）

## 4. 验证

- [x] 4.1 uv run pytest / ruff / mypy 全绿
