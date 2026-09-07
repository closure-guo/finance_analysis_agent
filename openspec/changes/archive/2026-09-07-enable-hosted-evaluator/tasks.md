# Tasks: enable-hosted-evaluator

## 0. 前置确认

- [x] 0.1 自托管 Langfuse 3.205.1 无 evaluator 公共 API（/api/public/eval-configs 返回
       SPA HTML）→ 按 spec 预设走降级方案（轮询 /api/public/scores）

## 1. 降级轮询实现

- [x] 1.1 失败测试先行：窗口聚合/阈值告警/口径比对（tests/evals/test_hosted_evals.py 6 例）
- [x] 1.2 evals/hosted_evals/poll.py：scores 拉取（窗口过滤/configId 过滤）+ 均分聚合 +
       低分 trace 清单 + 阈值告警（HOSTED_EVAL_ALERT_THRESHOLD 默认 3.5）
- [x] 1.3 口径对齐验证：同 trace hosted vs 离线 judge 打分 MAE（阈值 1.0，超限标漂移）

## 2. 治理

- [x] 2.1 evaluator 模板快照归档 docs/evals/hosted-evaluator-template.md（UI 配置后手工回填，等效版本管理）
- [x] 2.2 UI 配置真实 evaluator（4 个：report_relevance/debate_quality/decision_grounding/consistency，10% 采样）+ 回填 configId/模板快照（docs/evals/hosted-evaluator-template.md「已上线配置快照」）——LLM 余额可用，实证打分=4

## 3. 验证

- [x] 3.1 uv run pytest / ruff / mypy 全绿
- [x] 3.2 真实流量监控验证：/api/analyze 跑拓荆科技 → report_relevance 打分 4 落 score 库（见 tests/validation/2026-09-07-hosted-evaluator-e2e-validation.md）
