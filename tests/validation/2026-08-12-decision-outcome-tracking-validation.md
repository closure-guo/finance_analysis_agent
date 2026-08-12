# 人工验证报告: decision-outcome-tracking

**日期**: 2026-08-12
**验证人**: [待填]
**关联 delta**: openspec/changes/decision-outcome-tracking/
**E2E 门禁**: 不适用(纯后端旁路,非交互类变更,§2 判别)

## 验证结果

| Scenario | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|
| decision_log 建表 | init_decision_log 幂等建表 + 索引 | 单测锁定(test_idempotent_init/test_table_and_index_created) | ✅ |
| 结算规则正确 | 止损/目标/同日/超期/一字板/停牌/方向/基准 13 场景 | 单测锁定(test_settle.py 13 例) | ✅ |
| 幂等结算 | 重复 job 不重复结算/上报 | 单测锁定(test_idempotent_no_double_settle) | ✅ |
| 落库失败不阻断 | DB 异常业务正常 | 单测锁定(test_failure_does_not_raise) | ✅ |
| trace 不可查容错 | score 失败仅 WARN | 单测锁定(test_trace_missing_warns_not_raises) | ✅ |
| 真实决策落库 | 跑一次真实 deep 分析(approve),decision_log 有新行且 entry_price 为真实现价 | [待人工:approve 案例需真 LLM;可查 `sqlite3 data/sessions.db "SELECT * FROM decision_log"`] | ⬜ |
| approve-only 落库口径 | spec 原文「每个产出的 TradeDecision」与实现「仅 approve 落库」的措辞收窄(reject 决策流向 generate_report 但不落库) | [待人工:确认口径或要求补 reject 落库] | ⬜ |
| langfuse_trace_id 关联 | 落库行 trace_id 可在 Langfuse UI 打开对应 trace | [待人工:UI 核对] | ⬜ |
| 日批 job 真实结算 | 手动触发 settle_open_decisions() 对 open 行结算 + Langfuse 出现 3 个 score | [待人工:需真实行情 + open 决策] | ⬜ |
| scheduler 启动 | uvicorn 启动日志含「decision settle scheduler 已启动」;TESTING=1 不启动 | [待人工:启动后端核对日志] | ⬜ |

## 异常记录
[待填]

## 结论
[x] 存在待人工确认项(真实落库/trace 关联/日批结算/scheduler)
[ ] 全部通过,可 archive

## 备注
- 定时任务框架选型(APScheduler in-process,design 决策 6)**建议人工落 ADR 确认**——agent 不自建 ADR(AGENTS.md 红线)。
- 历史 TradeDecision 不回溯补录(design Migration Plan,Non-Goal)。
