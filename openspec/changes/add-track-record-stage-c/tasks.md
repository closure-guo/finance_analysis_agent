# Tasks: add-track-record-stage-c

## 1. 校准

- [x] 1.1 失败测试先行：分桶边界/neutral 处理/Brier 计算
- [x] 1.2 校准分桶 + Brier Score 计算与 API（/api/v1/track-record/calibration）
- [x] 1.3 校准页（校准曲线 + Brier 卡 + 分桶表，路由 /track-record/calibration）

## 2. 切片与详情

- [x] 2.1 四维切片引擎（行业静态映射/市值桶/市场环境 250 日均线信号/持有期桶）+ API /segments
- [x] 2.2 战绩页切片面板（四维桶表 + 样本不足标注）；外部数据源（市值/基准均线实盘值）未接入前「未知」桶如实展示
- [x] 2.3 观点详情 API /predictions/:id（快照/audit/判定 + daily_marks 盯市叠加序列）
- [x] 2.4 观点详情页前端 /track-record/predictions/:id（盯市叠加图/只读快照/判定卡/审计时间轴）

## 3. 版本与完整性

- [x] 3.1 agents 表 + 版本登记（register_agent 封存旧版）+ insert 自动归属活跃版本
- [x] 3.2 统计分段封存（P6）：overview version 参数，缺省当前活跃版本；响应带版本列表
- [x] 3.3 战绩页版本切换查看（多版本时渲染选择器，切换后 overview?version=N）
- [x] 3.4 rationale_snapshot 哈希（sha256 规范化 JSON，写入即冻结）+ integrity-check 日批（16:40）+ 审计日志（状态变更留痕 action=status_change，篡改留痕 action=integrity_mismatch）

## 4. 验证

- [x] 4.1 uv run pytest（全套 1857 passed）/ ruff / mypy 全绿
- [x] 4.2 前端 vitest 全绿；E2E 门禁 19 passed / 7 skipped（CI 镜像环境）
- [ ] 4.3 人工验证：切真实模型版本（register_agent）确认分段统计 + 校准页看真实 hit 率曲线