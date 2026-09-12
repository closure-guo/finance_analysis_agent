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
- [x] 2.2 UI 配置真实 evaluator（需 LLM 余额跑 judge 模型）+ 回填 configId/模板快照——2026-09-12 实测 4 条 ACTIVE、真实流量 4/4 COMPLETED 并落分（tests/validation/2026-09-12-hosted-evaluator-real-traffic-validation.md）；configId 实为 NULL（3.225.7），判别改 source=EVAL（commit 5e6008a），快照已回填修订注记

## 3. 验证

- [x] 3.1 uv run pytest / ruff / mypy 全绿
- [x] 3.2 真实流量监控验证（依赖 2.2 的 UI evaluator 上线后）——2026-09-12 通过（poll 报告 + 端到端落分）；口径对齐 32 对 MAE=1.0312 超 1.0 标 drift，归因=hosted 模板落后于离线 rubric（consistency 缺 v2 语义 / decision_grounding v3≠v6），处置（UI 模板升级）待 owner 拍板，见验证报告 §3
