# Proposal: add-event-delivery-resilience

## Why

incident 037：6 万+ thinking_token 把单消费者发布链路压出分钟级积压（SSE 消费端滞后 15.4 分钟），一次 ~2 秒的 SQLite 瞬断（`unable to open database file`）恰好落在积压排空窗口，R2 之后的节点事件永久丢失、终态事件从未发布——管线 17:10 已完成出报告，Langfuse 显示完成、前端冻结在 72%、聊天回复谎称「本次未返回有效报告内容」，三个界面三种说法。「分析完成」这一事实依赖事件链路端到端送达才成立，而当前链路在思考流洪峰 + 存储瞬态故障叠加下没有任何一层设防。

## What Changes

- **终态事件优先送达**：`done` / `report_ready` / `error` / `interrupted` 的持久化与发布不得与 thinking_token 明细批量队列竞争——终态落库带重试、发布前只须冲刷有界的 pending 缓冲（≤32 条单事务），会话状态流转与会话列表查询不再依赖 SSE 实时链路排空
- **发布积压可观测 + 背压**：事件队列深度 / 丢弃计数成为可观测指标；超阈值时允许丢弃 thinking_token 明细（计数 + 日志），节点边界、工具、终态事件 MUST NOT 丢弃——替换现有 `_put_event` 队列满静默吞事件的实现（`agent_factory.py:586-588`）
- **SQLite 瞬态错误重试**：`session_store._get_db` 对 `unable to open database file` / `database is locked` 做短重试，覆盖全部读写函数（现状仅 append 两函数有重试）；重试耗尽 MUST 显式抛错，不得静默丢写
- **空结果语义区分**：`run_deep_analysis` 管线异常终止时 MUST 返回显式错误 TOOL_RESULT（`is_error=True` + 机器可读 `pipeline_error` 标志 + 可读原因），MUST NOT 返回空串；harness 对空 output 按缺失处理；ReAct 摘要层不得将管线异常终止转述为「未返回有效报告内容」
- **超时判定基于管线真实完成状态**（2026-10-04 20:39 拓荆运行实证补充）：硬墙钟看门狗（`agent_factory.py:597`）在事件排空延迟下会把「图已完成但完成信号滞后 19 分钟」误判为超时——本次管线 21 分 09 秒即完成出报告，却在 21:19:02 被判超时置 failed。预算耗尽时 SHALL 先核对图的真实完成状态，已完成按完成处置；图完成后工具消费端 SHALL 压缩缓冲明细使终态有界送达

四项逐项独立验收（incident 037 处置纪律）+ 超时判定一项（20:39 案例补充），一次变更内按能力分文件交付。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `session-streaming`: 新增「终态事件优先送达」与「发布积压可观测与背压」两个需求——终态不得排在明细积压之后，明细可丢、边界与终态不可丢；不改动既有「seq 单调 + 先落库后 fan-out」「慢订阅者断开」「终态 per-run 去重」语义
- `session-persistence`: 新增「SQLite 瞬态错误重试」需求——连接获取层统一短重试，覆盖全部热路径写函数
- `deep-analysis-tool-feedback`: 新增「管线异常终止的工具结果显式错误语义」需求——异常终止与正常完成在 TOOL_RESULT 层机器可区分
- `pipeline-events`: MODIFIED「管线超时与中断检测」——超时判定须先核对图的真实完成状态，已完成不得判超时

## Impact

- 后端：`stream_registry.py`（终态发布路径 / 队列指标）、`agent_factory.py`（`_put_event` 背压策略、`run_deep_analysis` 终态 TOOL_RESULT）、`pipeline_runner.py`（终态冲刷顺序）、`session_store.py`（`_get_db` 重试）、`harness/loop.py`（空 output 处理）
- 前端：无新契约（现有 seq 守门 / resync / 终态处理语义不变，明细事件变稀疏对 UI 透明）
- 测试：新增积压背压、终态送达顺序、瞬断重试、空结果语义四组用例；`tests/test_pipeline_write_blocking.py` 等既有守卫不受影响
- 风险：thinking_token 明细在极端积压下降级为稀疏采样——UI 思考流密度降低，属可接受权衡（incident 037 教训：完成事实 > 明细完整性）
