# Tasks: resume-pipeline-across-sessions

> 前置：redesign-pipeline-hierarchical-timeline + fix-node-timer-real-lifecycle 已落地。
> 关键技术前提（实施第一步验证）：SSE 断开后 graph.stream 是否被 asyncio 取消中断。

## 0. 技术前提验证

- [x] 0.1 实测：启动管线后 abort SSE，观察后端 graph.stream 是否继续（日志/快照是否推进）。若被中断 -> 必须 PipelineRunner 后台化；若天然继续（独立线程 executor）-> 可简化方案

## 1. 后端：管线后台执行

- [x] 1.1 编写失败测试：PipelineRunner 启动幂等、SSE 断开后后台 task 继续推进
- [x] 1.2 新增 `pipeline_runner.py`：PipelineRunner 类（后台 asyncio task 执行 graph.stream，节点事件写会话事件队列 + 每节点完成写快照）
- [x] 1.3 `session_store.py`：sessions 表新增 pipeline_snapshot 列（迁移 ALTER TABLE）；update_pipeline_snapshot / get_session 返回快照
- [x] 1.4 `api.py`：管线启动改走 PipelineRunner.start；SSE 订阅事件队列（在线实时推送）；断开仅取消订阅不中断 task；后端启动时扫描 status=running 悬挂会话标记 failed

## 2. 后端：快照与恢复

- [x] 2.1 编写失败测试：每节点完成写 pipeline_snapshot；GET /api/sessions/{id} 返回 status + pipeline_snapshot
- [x] 2.2 实现快照持久化（layerTree 序列化 JSON）与恢复返回

## 3. 前端：序列化与恢复

- [x] 3.1 编写失败测试：serialize/deserializeLayerTree 往返一致；selectSession 按 status 恢复（running->时间轴+轮询、completed->报告+静态时间轴、failed->失败态）
- [x] 3.2 `pipelineTree.ts`：serializeLayerTree / deserializeLayerTree
- [x] 3.3 `App.tsx`：selectSession 改为按 status 分发恢复；条件化 abortStreaming（仅快速模式流）；running 会话轮询快照（2s，完成即停）

## 3.5 后端：ReAct 主链路快照接入（实施期补充，design.md §8）

> 背景：前端从不传 stockCode，真实主链路走 ReAct `run_deep_analysis` 工具，Task 1-3 的 fast path 接入对其不生效。

- [x] 3.5.1 编写失败测试：ReAct 工具执行期间会话 status=running 且 pipeline_snapshot 随节点事件推进；工具结束 status=completed；异常 status=failed
- [x] 3.5.2 `agent_factory.py`：`run_deep_analysis` 工具内维护快照（复用 pipeline_runner 的 build_layer_tree/apply_node_event，节点首现/node_complete/node_timing 写 update_pipeline_snapshot）；入口置 running、结束置 completed、异常置 failed；不改事件流

## 4. 验证

- [x] 4.1 后端 pytest / 前端 vitest 全绿
- [x] 4.2 ruff / tsc 全绿
- [x] 4.3 E2E：stub 管线运行中切换会话再切回 -> 时间轴恢复且快照不回退；完成后切回 -> 报告+静态时间轴；现有套件不回归
- [x] 4.4 人工验证报告落 `tests/validation/resume-pipeline-across-sessions-validation.md`（真实 LLM 下切换会话管线后台续跑 + 切回恢复）
