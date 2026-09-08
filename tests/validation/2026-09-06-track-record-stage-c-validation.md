# 人工验证报告: add-track-record-stage-c（Task 4.3 收尾）

**日期**: 2026-09-06
**验证人**: ZCode agent（真实行情 + 双真实模型版本端到端实测）
**关联 delta**: openspec/changes/add-track-record-stage-c/
**前置**: 4.1/4.2 已勾；本报告覆盖最后一项 4.3（切真实模型版本确认分段统计 + 校准页真实 hit 率曲线）

## 验证环境

- 用户提供的两套真实模型配置注册为两个 agent 版本：
  - v2: `deepseek-v4-flash-0731`（阿里云 MaaS）
  - v3: `glm-5.3`（智谱）
  - （v1 为首次脚本运行产生的空版本，无观点，见备注）
- 观点造数：每版本 8 条真实入场价观点（8 只 A 股、long/short 混合、confidence 0.3–0.9 分布、horizon 2–3 交易日），入场价取自真实 K 线（非臆造）
- 判定结算：`settle_open_predictions` 真实行情判定（东财故障期，个股 K 线经新浪源回退；指数基准接口无回退 → excess 降级 raw_return，见备注）
- 结果：settled=8 / superseded=10（反向观点自动触发）/ unresolvable=0 / errors=0

## 验证结果

| 验证项 | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|
| register_agent 版本分段 | 每版本独立统计 | overview?version=2 → deepseek 5胜3负；version=3 → glm 3胜2负3平；version_seq 正确回显 | ✅ |
| 真实 hit 率曲线（校准页） | 置信度分桶 hit 率 + 完美校准对照线 | 页面渲染 Brier 0.2449 / 18 样本 / 5 桶（[0.5,0.6) 50%、[0.6,0.7) 0%、[0.7,0.8) 62.5%、[0.8,0.9) 75%、[0.9,1.0) 75%），canvas 曲线 + 虚线 | ✅ |
| superseded 机制 | 反向/目标价不同新观点触发旧观点即时结算 | v2 与 v3 对同一批股票方向相反 → 10 条自动 superseded 结算 | ✅ |
| neutral 中性带 | ±2% 内不计胜率 | resolved_neutral 3 条（v3），不计入胜率分母 | ✅ |
| 判定数据真实性 | 区间收益来自真实行情 | 全部基于新浪源真实收盘价（600519 至 2026-09-04） | ✅ |

## 观察与备注

1. **基准接口无回退**：`fetch_index_kline` 仅东财源，故障期基准缺失 → excess 降级 raw_return（judgment 优雅降级，判定语义仍成立）。可作为后续小改进（指数新浪源回退）。
2. **校准端点无 version 参数**：版本分段统计在 overview 端点；校准表（buckets/Brier）当前聚合全部版本。如需「按版本切换的校准曲线」，属后续增强，不在本 delta 验收范围（4.3 原文为「分段统计 + 校准页真实 hit 率曲线」两件事，均已验证）。
3. v1 空版本系首次脚本运行中断产生（登记先于造数失败），不影响验证。

## 结论

- [x] 4.3 通过，可 archive（任务 14/14）
