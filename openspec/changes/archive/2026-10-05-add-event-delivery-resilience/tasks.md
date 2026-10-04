# Tasks: add-event-delivery-resilience

- [x] 终态事件优先送达：`StreamRegistry.publish_terminal` 落库重试 + 冲刷后发布收拢全部终态发布点；单测模拟明细洪峰下 `done` 落库/发布/`sessions.status` 流转有界完成，重连客户端重放即见终态
- [x] 发布积压可观测与背压：`_put_event` 分类处置（明细可丢+计数+节流日志，边界/工具/终态阻塞入队不丢弃）+ `PipelineRunner` pending 上限 + `backlog_stats()` 可查询；单测覆盖队列满三类事件的分流处置与静默丢弃清零
- [x] SQLite 瞬态错误重试：`_get_db` 瞬态模式短重试覆盖全部读写函数；单测 monkeypatch 连接抛 `unable to open database file` 验证自愈窗口内成功、耗尽显式 raise；非 append 热路径（update_session_status / update_pipeline_timelines / update_pipeline_snapshot）同受保护
- [x] 空结果语义区分：`run_deep_analysis` 全退出路径最终 TOOL_RESULT 非空 + 异常终止挂 `pipeline_error` 标志；`loop.py` 空 output 按失败处理不置 `analysis_completed`；单测覆盖超时/中断/空串三场景，阻断终态（pipeline_blocked）与正常完成契约回归
- [x] 超时判定基于图真实完成状态（2026-10-04 20:39 拓荆案例）：预算耗尽时先核对图完成信号，已完成按完成路径处置（交付报告/正常终态/completed）不判超时；图完成后消费端压缩缓冲明细；单测覆盖「图完成+排空滞后」不误判、「图未完成」仍判超时两分支
- [x] 既有语义回归：test_stream_registry / test_terminal_cas / test_session_events_batch / test_pipeline_write_blocking / test_deep_analysis_tool / test_api_blocked_terminal 全绿（去重、seq 单调、先落库后 fan-out、慢订阅者断开不回退）
- [x] 人工验证报告落 `tests/validation/`：真实深度分析（思考量大的标的）+ 故障注入核对终态可见性与会话状态一致性，三界面（Langfuse / 管线 UI / 聊天回复）说法归一
