# 跨模型一致性校准验证（2026-09-07）

> 本报告是 agent-evaluation-suite / add-judge-human-calibration 归档的校准环节证据。
> **口径**：首轮校准以「跨模型一致性门禁」代理完成（人工标注延后——人工环节仍需
> 资源，工具链已就绪，回填 human_score 后重跑 measure.py 即可闭合 spec 要求）。

## 一、工具链验证

| 项 | 结果 |
|---|---|
| 校准导出 CLI（`tests/scripts/judge_calibration_export.py`） | ✅ 修复 sys.path 崩溃 + 采样改 scores 端点按维度名聚合；产出 90 行/30 trace，judge_score 全非空 |
| 标注材料 | ✅ `evals/judge_calibration/data/judge-sample-round1.jsonl`（含 trace_url 项目作用域直链 + judge_reason） |
| measure.py 一致性计算 | ✅ 单测 9 例全绿（Spearman/MAE/方向一致率/阈值） |
| 跨模型重评脚本 | ✅ `tests/scripts/judge_cross_model_rerun.py`（续跑分批/温度降级/第三方端点） |

## 二、三模型交叉重评（90 对）

样本：30 trace（`a-share-analysis-v1` 实验运行，08-24/25 离线 judge 打分）× 4 维度。

| 维度 | deepseek↔qwen | deepseek↔k3 | 说明 |
|---|---|---|---|
| report_relevance | Spearman 0.87 / MAE 0.10 / 方向 93% | — | ✓ 稳定 |
| consistency | Spearman 0.28 / 方向 80% | — | 同级细分分歧 |
| debate_quality | Spearman -0.12 / 方向 95% | — | 仅 4↔5 细分 |
| decision_grounding | **方向 50%** / MAE 0.95 | **方向 85%** / MAE 0.45 | qwen 严格读法离群 |
| **整体** | Spearman 0.63 / MAE 0.48 / 方向 81% | — | 过代理门禁阈值 |

decision_grounding 分歧归因：qwen 将「执行纪律参数（止损/阈值/仓位）缺失出处」判为
无中生有（1-2 分），deepseek/k3 判为个别细节（扣 ≤1 分）；10 个分歧局 k3 站 deepseek 7 次。
rubric v3 建议增补执行纪律锚点（见 `reports/judge-cross-model-report-20260907.md`）。

## 三、附带修复

- **incident 025**：opencode zen/go 网关强制 `x-opencode-session` 头，离线 judge 全挂约两周；
  适配器补头修复（TDD 3 例，真实调用复验通过）。
- kimi k3-256k 端点接入（OpenAI 兼容、仅允许 temperature=1，脚本温度降级）。

## 四、遗留（延后项，非阻塞）

1. 人工打分 ≥30 条 → measure.py 一致性报告（spec「人工标注工具/judge-人工一致性指标」）仍开放。
2. decision_grounding rubric v3 修订（增补执行纪律锚点）后重测——修订走 prompt-deploy 管线后按
   3.2 强制校准约定执行。