# Incident 020: 深研管线「假卡死」— 事件落库限速终态迟到 + 管线超时空转

**日期**: 2026-08-25
**环境**: Windows Docker Desktop 卷 / SQLite WAL / 方舟 GLM-5.3 / Langfuse 3.205.1
**影响**: 601700 深研会话（d9a2748e-ac2）管线真实执行 71 分钟完成后，会话永远
`running`、前端永远收不到报告；期间用户视角「管线卡住」。
**状态**: 已修复（批量落库 + 墙钟超时）；放大器另经 delta
`improve-analyst-throughput` 治理

## 现象

- 用户报告「深度研究股票分析管线卡住了」，Langfuse trace
  `00c9d4a279fd2064cd495230320e50dd`（deep_analysis:风范股份）
- trace 实际 13:43:52→14:54:59Z 跑完并产出完整报告（root span 已关闭）
- 但会话状态一直 `running`；journal（session_events）在 trace 关闭后仍在
  以 ~70 事件/分钟龟速写入 bull/bear 辩论 token，滞后真实执行 45 分钟且持续扩大
- `report_ready`/`done` 终态事件压在积压尾部，永远到不了前端

## 根因（三层叠加）

**层 1（直接根因，假卡死）**：每条 SSE 事件（含每个 thinking token）经
`registry.publish → asyncio.to_thread(append_session_event)` 独立事务落库，
每次新建连接 + BEGIN IMMEDIATE + commit(fsync) + close。Windows Docker 卷
上实测单条 **75.8ms**；运行中叠加 `update_pipeline_timelines`（每 0.5s 全量
序列化，fast path 无节流逐 token 全量写）等多个 writer 抢 SQLite 写锁，
实际 ~860ms/条。本次 28,692 条 thinking_token → 消费端小时级积压。

**层 2（放大器，71 分钟）**：
- `technical_analyst` 250 期全窗口指标 JSON 进 prompt，单次 LLM 调用
  11.5~14 分钟（其余分析师 20s~3min）
- citation 三轮失败率 35%→38%→31%（系统性 claim/field_ref 不匹配，重试零收益），
  每轮仍全量重跑 4 分析师并等最慢的 technical，白烧 ~40 分钟
- fund_manager 退回一次多跑一轮 trader+风控（~19 分钟）

**层 3（护栏失灵）**：ReAct 路径管线超时实现为
`wait_for(chunk_queue.get(), timeout=...)` 的**单次空闲**超时——thinking token
持续流动时永不触发，71 分钟无人拦截（fast path 是正确墙钟语义，ReAct 路径漏改；
spec pipeline-events「管线超时与中断检测」早已要求全局超时）。

## 排查方法（可复用）

双时间线对照法：Langfuse observation 时间戳（生产端线程全速、真实）vs
session_events journal 时间戳（消费端落库、被限速）。两者在 R3 technical 完成
后开始分叉（+4.5min → +7min → +45min 单调扩大）即为消费端积压的铁证；
后端日志「temperature 白名单剔除」行（每次 LLM 调用一条）证明 14:54:32 后
已无 LLM 调用 → journal 尾部事件只能是积压重放。容器内直接压测
`append_session_event` 30 条量化单条耗时。

## 修复

1. `session_store.append_session_events` + `stream_registry.publish_many`：
   整批单事务分配连续 seq，「先落库再 fan-out」契约不变；api.py ReAct 循环与
   PipelineRunner fast path 对 thinking_token 缓冲批量（32 条/批，边界事件与
   心跳即冲刷，终态发布前必冲刷）
2. PipelineRunner 逐 token 时序写按 0.5s 节流（对齐 agent_factory 既有修复
   标准），结束时补写
3. ReAct 路径超时改墙钟剩余预算（`59dd920`）
4. 放大器治理（delta `improve-analyst-throughput`）：技术指标裁剪最近 60 期 +
   citation 失败率停滞提前放行（`f808c94`）

## 关联

- delta spec: `openspec/changes/improve-analyst-throughput/`
- 预存在测试隔离地雷顺带修复：`api.TESTING` 模块级冻结常量与导入顺序耦合
  （test_pipeline_stub.testing_env 显式 patch）
- 未修（记录）：akshare fetch 阶段 ConnectionError 重试（网络环境问题）；
  aiohttp `Unclosed client session`（第三方库泄漏，src 无直接引用）
