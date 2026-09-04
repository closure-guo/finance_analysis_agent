# Tasks: add-judge-human-calibration

## 1. 标注工具

- [ ] 1.1 失败测试先行：导出表结构与一致性计算
- [ ] 1.2 抽样导出脚本（quick/deep 双模式覆盖，每轮 ≥30 条）
- [ ] 1.3 标注表格式 + 仲裁流程说明

## 2. 一致性指标

- [ ] 2.1 Spearman/MAE/方向一致率计算
- [ ] 2.2 校准报告生成（reports/）

## 3. 校准回路

- [ ] 3.1 阈值配置化 + 低于阈值触发 judge prompt 修订流程
- [ ] 3.2 judge prompt 变更后强制校准 + 结论归档 docs/evals/

## 4. 验证

- [ ] 4.1 uv run pytest / ruff / mypy 全绿
- [ ] 4.2 首轮真实标注 + 校准报告（人工环节）
