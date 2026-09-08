# add-track-record-stage-c 验证报告

- 日期：2026-09-04
- 提交：417fd28（后端：校准/切片/版本分段/完整性）+ ee1159c（前端：版本切换/切片面板/详情页）

## 自动化验证

- 全套后端 pytest：1912 passed（stage-c 新增 24 例：快照哈希稳定性、agents
  登记封存流、审计写入/不变更不写、integrity_check 篡改检出、校准分桶边界/
  neutral 处理/Brier、四维切片桶、市场环境信号、API calibration/segments/
  detail 404/overview 版本参数）
- 前端 vitest：trackRecord 20/20（校准页 4、版本切换/切片/行跳转 3、详情页 5、
  既有 8）
- E2E 门禁 19/7/0；ruff / mypy 全绿；delta 过 strict

## 已实现行为核对

- 版本分段（P6）：register_agent 旧版自动封存；overview 缺省取当前活跃版本
  （无 agent 时统计全部，兼容既有数据）
- 快照冻结：hash = sha256(规范化 JSON)，写入即存；篡改 → integrity_mismatch
  审计 + 日批告警（16:40）
- 幂等迁移：旧库 ALTER TABLE 补 version_seq/snapshot_hash；缺 agents/audit_log
  表时落库/判定不阻断（增强字段容错）

## 待人工验证

1. 真实模型版本切换：register_agent 登记新版本后，/track-record 统计分段是否
   符合预期（需真实模型变更场景）
2. 校准页真实 hit 率曲线（需足够 resolved 样本 + 真实置信度）
3. 切片面板的市值/市场环境维度（外部数据源接入后启用，当前如实归「未知」）
