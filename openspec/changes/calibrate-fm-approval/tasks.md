# Tasks: calibrate-fm-approval

## 1. 取证

- [ ] 1.1 从 Langfuse trace + 战绩库统计 FM 决策历史分布，定位 prompt 层 vs 数据层根因
- [ ] 1.2 结论落报告（reports/ 或 validation）

## 2. Prompt 校准

- [ ] 2.1 fund_manager.md 明确三档判定标准 + 不得无限期回避决策约束 + 示例锚点
- [ ] 2.2 scripts/deploy_prompts.py 发布（HEAD 判别预检）

## 3. 评估接入

- [ ] 3.1 失败测试先行：分布统计与双向门禁断言
- [ ] 3.2 fm_decision_distribution 指标 + 人工抽检一致率
- [ ] 3.3 双向门禁阈值配置化，纳入 nightly @live

## 4. 验证

- [ ] 4.1 uv run pytest / ruff / mypy 全绿
- [ ] 4.2 真实链路人工验证 FM 可产出 approve（Langfuse trace 佐证）
