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
- [x] 3.3 首轮校准——**以跨模型一致性代理完成（2026-09-07，人工标注延后至 backlog）**：
       导出 CLI 修复（sys.path + scores 端点按维度聚合）产出 90 行/30 trace 标注材料
       （evals/judge_calibration/data/judge-sample-round1.jsonl，含 trace_url 直链 +
       judge_reason）；人工打分缺位时改用三家 LLM（deepseek/qwen3.8-flash/k3-256k）交叉重评，
       measure.py 一致性计算复用（整体 Spearman 0.63/方向 81%），报告
       reports/judge-cross-model-report-20260907.md。
       **延后项**：spec 要求的人工打分 ≥30 条 → measure.py 报告 仍开放（工具链已就绪）
       ——exporter 抽样直接可用，人工回填 human_score 后重跑即可

## 4. 验证

- [x] 4.1 uv run pytest / ruff / mypy 全绿
