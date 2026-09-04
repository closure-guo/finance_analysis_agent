# Tasks: enable-hosted-evaluator

## 0. 前置确认

- [ ] 0.1 确认自托管 Langfuse 版本是否支持 managed evaluator，不支持则定降级方案（轮询脚本）

## 1. 启用与口径

- [ ] 1.1 失败测试先行：分数命名空间与口径比对
- [ ] 1.2 配置 hosted evaluator（采样率默认 10%）+ 模板对齐离线维度
- [ ] 1.3 口径对齐验证（同 trace 双打分 MAE 阈值）

## 2. 告警与治理

- [ ] 2.1 均分阈值告警（webhook 或轮询）+ 低分 trace 清单
- [ ] 2.2 evaluator 模板纳入 prompt 部署纪律

## 3. 验证

- [ ] 3.1 uv run pytest / ruff / mypy 全绿
- [ ] 3.2 真实生产流量抽样打分验证（人工看板核对）
