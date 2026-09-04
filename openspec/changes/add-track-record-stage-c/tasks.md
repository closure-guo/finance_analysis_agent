# Tasks: add-track-record-stage-c

## 1. 校准

- [ ] 1.1 失败测试先行：分桶边界/neutral 处理/Brier 计算
- [ ] 1.2 校准分桶 + Brier Score 计算与 API
- [ ] 1.3 校准页（校准曲线 + Brier 成对展示）

## 2. 切片与详情

- [ ] 2.1 四维切片指标（行业/市值/市场环境/持有期，牛熊判定）
- [ ] 2.2 战绩页切片面板
- [ ] 2.3 观点详情页 /predictions/:id（叠加图/快照/判定卡/时间轴）

## 3. 版本与完整性

- [ ] 3.1 agents 表 + 版本登记流程
- [ ] 3.2 统计分段封存（P6）与版本切换展示
- [ ] 3.3 rationale_snapshot 哈希 + integrity-check 日批 + 审计日志

## 4. 验证

- [ ] 4.1 uv run pytest / ruff / mypy 全绿
- [ ] 4.2 E2E：校准页/详情页/版本切换
- [ ] 4.3 人工验证报告落 tests/validation/
