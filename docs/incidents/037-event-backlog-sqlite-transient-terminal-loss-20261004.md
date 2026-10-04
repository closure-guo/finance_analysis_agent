# Incident 037: 事件发布积压 + SQLite 瞬断——管线已完成但三个界面三种说法

**日期**: 2026-10-04
**状态**: 已登记（根因定位完成，修复待立项）
**关联**: [021（假卡死同族）](021-deep-analysis-session-stuck.md)、[014（高频 SQLite 写冻结）](014-refresh-clears-session-list-20260716.md)、[013（并发写 DB 数据丢失）](013-sse-concurrent-text-corruption-20260804.md)、`llm-output-resume`/`stream-store` spec

## 症状

会话 `5faf1d4b-072`（拓荆科技，16:52:16 发起）同时出现三个互相矛盾的事实：

| 界面 | 显示 | 真相 |
| --- | --- | --- |
| Langfuse | 分析完成，已产出报告 | ✅ 正确（根 span 17:10:21 关闭，报告 17:10:13 落盘） |
| 前端管线 UI | 冻结在「17:13:48 引用校验完成」 | 事件流滞后 **15.4 分钟**（引用校验服务端 16:58:24 就完成了） |
| 聊天回复 | 「本次未返回有效报告内容，建议重新分析」 | ❌ 错误——报告文件完好，是事件流死了 |

journal 证据：60,750 条 thinking_token；风控 R2 之后所有节点事件（R2/judge/
fund_manager/report）**永久缺失**；`tool_result run_deep_analysis result=''`；
无任何终态事件（done 由 react 层兜底发布）；会话终态 `clarifying`、
`report_markdown` 空。

## 根因（积压 × 瞬断的位置巧合）

1. **发布链路积压（021 同族复发）**：6 万+ thinking_token 把单消费者发布
   队列压出分钟级滞后——节点事件 journal 落库滞后 ~2.5 分钟（aggressive_r1
   服务端 17:05:47 完成 vs journal 17:08:24），SSE 消费端滞后 15.4 分钟。
   021 的批量落库修复治了「单条事务 fsync 限速」，没治「总量超过消费速率」。
2. **SQLite 瞬断（新变量）**：17:16:49.5 起 ~2 秒，容器内
   `sqlite3.OperationalError: unable to open database file`（`_get_db` 的
   `PRAGMA journal_mode=WAL` 处），命中 list_sessions（前端轮询 500）、
   `_background_consume`（update_pipeline_timelines / update_session_status
   均失败，Task exception was never retrieved），17:16:59 done 事件落库成功
   = 已自愈。Windows 宿主机 ↔ WSL2 bind mount 上跑 WAL 属官方不支持的
   跨网络文件系统场景。
3. **位置巧合**：瞬断恰好落在「积压排空、终态事件待发」的窗口——积压的
   R2+ 节点事件被永久截杀，`run_deep_analysis` 事件流异常终止返回空串，
   react 层基于空结果生成了误导性回复。

**排查操作纪律反思**：本次排查期间曾从 Windows 宿主机用 sqlite3 直读容器
正在写入的 WAL 库——与 SQLite 跨网络文件系统的官方限制相抵触，**不能排除
为瞬断诱因之一**。今后排查生产库一律容器内执行或快照后离线读。

## 修复方向（待立项，逐项独立验收）

1. **终态事件旁路**：done/report_ready/error 走独立优先通道，不与
   thinking_token 批量队列竞争（完成事实不允许排队）
2. **积压可观测**：registry 队列深度/滞后时长指标 + 背压（超阈值丢弃
   thinking_token 明细，保节点边界与终态）
3. **SQLite 瞬态重试**：`unable to open database file` / `database is locked`
   在 `_get_db` 层做短重试
4. **空结果语义区分**：`run_deep_analysis` 事件流异常终止时 MUST 返回显式
   错误（区分「管线异常终止」与「正常无报告」），react 层不得将异常终止
   转述为「未返回有效报告内容」

## 教训

- 「分析完成」这个事实依赖事件链路**端到端送达**才成立——服务端完成 ≠
  任何界面能看见完成。三个界面三种说法 = 观测面分裂，排查必须回到
  Langfuse/journal 对时（AGENTS.md 红线「排查必须同时查后端日志和
  Langfuse trace」的再验证）
- 管线 UI 快照持久化滞后于真实进度（本例停在 72% 而实际已到报告）：
  快照不可作为「管线卡在哪」的判据，只能作参考
- pipeline_snapshot 的 UI 进度与 Langfuse span 冲突时，以 Langfuse 为准
