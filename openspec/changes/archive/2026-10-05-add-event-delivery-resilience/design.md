# Design: add-event-delivery-resilience

## Approach

四项修复各自独立、可逐项验收，共享一个原则：**完成事实的可靠性高于明细完整性**（incident 037 教训）。以下代码事实引自 incident 037 排查与链路勘察（2026-10-04）。

### 1. 终态事件优先送达（session-streaming）

现状：终态与 thinking_token 共用同一条链路——ReAct 路径逐事件 `registry.publish`（`api.py:1660`，每次一个 SQLite 单事务），fast path 终态在 `PipelineRunner._run` 的超时/异常/finally 分支（`pipeline_runner.py:373-391, 453-488`）。终态排在积压排空之后。

方案：新增 `StreamRegistry.publish_terminal(session_id, event)`，作为所有终态发布的唯一入口：

1. per-run CAS 去重复用现有 `_try_mark_terminal`（`stream_registry.py:93-111`），去重语义不变；
2. **先冲刷生产者 pending 明细缓冲再落库终态**——pending 缓冲有界（≤32 条，`TOKEN_BATCH_MAX`），单事务冲刷耗时可控，保证 `(session_id, seq)` 单调不被终态跳号破坏（跳号会触发前端 resync，而 resync 读 journal 时明细尚未落库会被 seq 守门丢弃——这是「完全旁路不保序」方案的坑，不采用）；
3. 终态 journal 写入带更重的重试（见 §3），成功后立即 fan-out；
4. 调用方收拢：`pipeline_runner._run` 三分支 + `api._run_react_analysis` / `_run_chat_task` 的 done/error 发布点全部改走 `publish_terminal`；`sessions.status` 流转与终态发布同窗（现状已同窗，补重试即可）。

不改「先落库后 fan-out」（`session-streaming` ③）与慢订阅者断开语义。已连接的慢 SSE 客户端 HTTP 层仍要排空其历史帧——这一滞后由 §2 背压从源头限流，终态旁路负责的是**落库确定性**与**新连/重连客户端立即见终态**。

### 2. 发布积压可观测与背压（session-streaming）

现状：`_put_event` 用 `put_nowait` + `contextlib.suppress(asyncio.QueueFull)`，队列满**静默吞掉任何事件**（`agent_factory.py:586-588`）；`PipelineRunner` 的 pending 缓冲无上限（`pipeline_runner.py:342`）。

方案（分类背压，改 `_put_event` 与 pending 缓冲两处）：

- **thinking_token**：队列满直接丢弃，per-session 丢弃计数 + 节流日志（首条全量、后续每 100 条采样一条，含 session_id 与累计丢弃数）；
- **节点边界 / 工具 / 搜索 / 终态事件**：改为 `await event_queue.put(ev)` 阻塞入队（不丢弃）。生产端阻塞的内存代价由上游 `chunk_queue`（无界，`:549`）吸收——节点级事件量级为几十条/次分析，无界增长风险可忽略；
- **PipelineRunner pending 缓冲加上限**（如 512 条）：超限丢最旧 thinking_token，同样计数 + 日志。

可观测：丢弃计数与队列深度进节流日志；`StreamRegistry` 增加轻量 `backlog_stats()`（per-session 队列深度 / 丢弃计数快照），挂到现有 ops 控制台既有指标面（`ops_api.py`），不做新端点。

### 3. SQLite 瞬态错误重试（session-persistence）

现状：`_get_db`（`session_store.py:61-67`）每次新建连接，无任何重试；仅 append 两函数有重试（`:32-33, 330-334, 376-380`）；`busy_timeout=15s` 只覆盖 `database is locked` 的等待窗口，`unable to open database file`（bind mount 瞬断）直接抛出。

方案：`_get_db` 内对 connect + 两条 PRAGMA 包重试循环——捕获 `sqlite3.OperationalError` 且消息命中瞬态模式（`unable to open database file` / `database is locked` / `disk I/O error`），最多 4 次、退避 0.1/0.2/0.4s（总窗口 ~0.7s + 每次 connect 超时）。所有函数自动受益。重试耗尽 raise 原异常。

终态关键路径调用方（`publish_terminal` 落库、`update_session_status` 终态流转、`update_session_report`）在 except 中 `logger.exception` 显式留痕；`publish_terminal` 额外做 5 次 × 1s 的重试兜底（终态落库值得比普通写更固执）。

**不采用**：连接池/常驻连接（WAL 在 Windows↔WSL2 bind mount 上本属官方不支持场景，常驻连接会把瞬断放大成长期句柄失效；重试是针对性最小修复）。**排查纪律**（incident 037 教训）：生产库一律容器内操作，本 delta 不涉及。

### 4. 空结果语义区分（deep-analysis-tool-feedback）

现状：harness 对**缺失** TOOL_RESULT 有兜底（`loop.py:592-598`，`[错误] 流式工具未返回结果` + `is_error=True` + 不置 `analysis_completed`）；但对 **output 为空串** 的 TOOL_RESULT 无守卫（incident 037 journal 实证 `run_deep_analysis result=''`），react 摘要 LLM 拿到空输入自行发挥出「本次未返回有效报告内容」。

方案：

1. `run_deep_analysis` 收尾保证：任何退出路径（正常/超时/异常/事件流中断）yield 的最终 TOOL_RESULT **output 非空**——累积结论为空时输出 `[错误] run_deep_analysis 管线异常终止（<原因>）`，metadata 挂 `pipeline_error=True`（超时/阻断路径既有标志保持）；
2. `loop.py`：TOOL_RESULT output 为空（strip 后）按缺失处理——替换为同款错误 ToolResult，`analysis_completed` 不置位；
3. 摘要轮输入材料即 TOOL_RESULT 文本本身——异常标志（可读原因 + metadata 转述）随工具输出进入上下文，摘要 LLM 据此陈述「分析异常终止」；`deep_mode.md` 摘要提示词若需配合措辞约束，走 agent-prompt-contracts 另行微调，不在本 delta 范围。

### 5. 超时判定基于图真实完成状态（pipeline-events，2026-10-04 20:39 案例补充）

实证：20:39 拓荆运行 glm-5.3 产生 6.97 万 thinking_token（同标的 20:00 运行仅 276 条，250 倍方差），Langfuse 根 span 证明管线 **21 分 09 秒完成**（预算内）、报告 21:00:26 落盘，但事件排空滞后 ~19 分钟——硬墙钟看门狗（`agent_factory.py:597`，消费循环内 `_remaining = pipeline_timeout - elapsed`）在 21:19:02 预算耗尽时误判超时，会话置 failed + 超时 TOOL_RESULT，33 秒后 `done` 才排空。报告完好却被判「未生成有效报告」。

方案：

1. **看门狗补完成核对**：预算耗尽分支在 raise TimeoutError 前，先核对图的真实完成信号——图流生成器已结束（生产端哨兵已被消费）或报告已落盘，则走完成路径（正常 TOOL_RESULT + completed 状态），MUST NOT 判超时；仅图确实未完成才维持超时语义；
2. **图完成后压缩消费**：`_background_consume` 在图完成信号到达时，对 `event_queue`/`chunk_queue` 中缓冲的 thinking_token 明细压缩丢弃（边界/工具/终态保留），使终态 TOOL_RESULT 秒级产生而非等排空——这也是看门狗「先核对再判」能拿得到及时信号的前提；
3. 与 session-streaming「终态事件优先送达」互补：发布层（journal/fan-out）与消费层（工具循环）双侧保证完成事实端到端送达。

## Alternatives Considered

- **event_queue 改无界**：不解决 journal 逐条写的限速与 SSE HTTP 洪峰，且引入无界内存风险；分级背压才是对症的。
- **终态完全绕过 seq / 不落 journal**：破坏重放顺序与前端 seq 守门（空洞触发 resync 时明细未落库 → 终态后到达的明细被当 stale 丢弃），否决。
- **SSE 层对 thinking_token 降采样**（消费端限流）：治标——journal 落库侧同样会被洪峰拖慢；从生产端分类背压更彻底。
- **SQLite 常驻连接池**：见 §3，bind mount 场景下反而放大故障面。

## Risks

- **UI 思考流变稀疏**：极端积压下 thinking_token 被丢弃，思考流密度下降。可接受（明细是装饰性输出，`chat-stream` spec 明文禁止进度走 thinking_token 旁路，进度语义由节点事件承载）；丢弃计数提供审计。
- **阻塞入队造成生产端停顿**：节点/工具事件阻塞等待队列空位，若消费端长期僵死会卡住图流线程。缓解：消费端是同一任务的 journal 写链路，`_get_db` 重试 + busy_timeout 提供有界等待；极端情形由管线 40 分钟超时兜底。
- **终态先于明细到达前端**：seq 跳号触发 resync，resync 读 journal 拿不到未落库明细。已由 §1.2 的「冲刷后再发终态」消除了大部分；残余窗口（缓冲冲刷成功但 fan-out 慢）由前端既有 resync 降级（刷新会话详情）兜底。
- **重试放大瞬时写放大**：0.7s 窗口内最多 4 次连接尝试，量级可忽略。
