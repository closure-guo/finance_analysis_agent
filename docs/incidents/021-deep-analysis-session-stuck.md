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

## 修复后复查（2026-08-26 上午，带修复重启后的首次真实运行）

墙钟超时/裁剪/降级均按设计生效（technical 3.7min vs 昨日 11.5min；超时精确
601s 触发），但暴露三个后续缺陷，已修：

1. **超时空 TOOL_RESULT**：超时分支只发 PROGRESS 不发 TOOL_RESULT，Agent
   上下文里工具结果为空 → 误判「临时故障」盲目重试、用户看不到失败原因。
   修复：超时/异常分支均发携带原因与 PIPELINE_TIMEOUT_SECONDS 指引的
   TOOL_RESULT。
2. **方舟文本格式工具调用泄漏**：Agent 的重试意图以
   `<tool_call>NAME<arg_key>K</arg_key><arg_value>V</arg_value></tool_call>`
   文本输出（方舟 GLM 原生格式，非结构化 tool_calls），harness 不识别 →
   XML 直接作为最终回答流给用户、重试从未执行。修复：新增流式识别过滤器
   `harness/ark_tool_call_text`（有界保持、跨增量识别、未闭合块原样返回），
   chat_stream 将其转为结构化工具调用执行（delta `parse-ark-text-tool-call`）。
3. **超时后孤儿图线程继续烧 LLM**：executor 线程无法强杀，消费端停止后
   生产端继续拉流（R2 分析师又跑了 3 分钟）。修复：`graph_cancel` 协作式
   取消——超时/异常置位后生产端在下一 chunk 停止拉流并 close 生成器。
4. **failed 被 clarifying 覆盖**：超时置 failed 后，`_run_react_analysis`
   收尾因 analysisExecuted=False 走澄清分支覆盖状态并发 awaiting_input。
   修复：收尾读取当前状态，failed 终态保留、不发 awaiting_input。

5. **错误观测缺口**：同步流式/非流式路径错误收口只落异常类名
   （metadata.error_type），消息文本仅存进程内事件——Langfuse 上 ERROR 级别
   无原因可读（汉森制药 002412 复盘：截断+升级重试两连败原因全靠代码还原）。
   修复：complete_stream 三个错误出口与 complete_text 异常分支对齐 async
   路径，落 output.error + status_message（截断含预算说明，异常路径保留
   部分正文）。

6. **截断升级重试从头重跑浪费**：升级层（call_llm_streaming）收到截断后
   用原始 messages + 131072 从头重生成（汉森制药 17 分钟部分正文被丢弃、
   重跑 34 分钟再失败）。修复（delta `truncation-escalate-resume`）：升级
   改走 gateway 续写机制——携带首轮正文尾部 + 翻倍剩余配额，两轮拼接返回。

## 关联

- delta spec: `openspec/changes/improve-analyst-throughput/`、
  `openspec/changes/parse-ark-text-tool-call/`
- 预存在测试隔离地雷顺带修复：`api.TESTING` 模块级冻结常量与导入顺序耦合
  （test_pipeline_stub.testing_env 显式 patch）
- 未修（记录）：akshare fetch 阶段 ConnectionError 重试（网络环境问题，已由
  fetch_benchmark_kline 回退链缓解——沪深300 失败自动切中证800/中证500，
  其余接口仍走既有 N/A 降级）；aiohttp `Unclosed client session`（第三方库
  泄漏，src 无直接引用）
- 遗留观察：单节点生成耗时方差大（3.7~15.7 分钟实测，端点侧问题）
  → 默认预算经 delta `raise-pipeline-timeout-default` 上调至 2400s（40 分钟），
  覆盖合法 R1+R2 双轮最坏包络；极端场景仍可经 PIPELINE_TIMEOUT_SECONDS 覆盖
