# Proposal: resume-pipeline-across-sessions

## Why

开启股票分析管线后切换会话，管线 UI 永久消失，用户无法回看或跟踪分析进度。

**根因**：`selectSession` 完全重置前端状态——`abortStreaming()` 中断 SSE 流、`pipelineMsgRef.current = null`、仅恢复 `report` 消息 + `chat_history` 对话，**不恢复管线 UI**（`type='pipeline'` 的分层时间轴状态树）。管线运行中切换会话即丢失全部管线状态。

用户期望：切换会话时管线在**后台继续跑**，切回该会话时恢复管线 UI（运行中则恢复实时进度，已完成则显示报告）。

## What Changes

- **后端会话级管线状态**：管线运行期间，将会话标记为 `status='running'` 并持久化当前管线进度快照（layerTree 序列化状态：各节点 status/startedAt/durationMs/currentNodeId），定期（每节点完成时）写入 session_store。
- **后台继续执行**：前端 abort 断开 SSE 时，后端 LangGraph 管线**继续执行**（不因客户端断开而中断）；完成后照常写 session 的 report/agent_process/analyst_reports。
- **切回恢复**：`GET /api/sessions/{id}` 返回管线状态快照与运行状态。前端 `selectSession`：
  - 若会话 `status='running'` 且有管线快照 → 重建分层时间轴（恢复 layerTree），标记运行中节点，并可选择重新订阅进度（轮询快照或重连 SSE）。
  - 若 `status='completed'` → 恢复报告 + 已完成的静态分层时间轴（从 agent_process 或快照重建，供回看各节点耗时与摘要）。
  - 若 `status='failed'` → 显示失败状态。

## Non-goals

- 不改变管线执行逻辑、节点定义、事件契约（node_start/node_complete/node_timing 等不变）。
- 不改变快速模式（无管线 UI）。
- 不实现多客户端同时订阅同一管线（单用户单会话恢复即可）。
- 不改变既有报告恢复（report 消息）与 chat_history 恢复逻辑。

## Alternatives Considered

| 方案 | 评估 |
|------|------|
| 仅恢复已完成静态时间轴（中断运行管线） | 切换即丢失运行中的分析，违背"后台继续跑"诉求 |
| 前端 localStorage 缓存 layerTree | 换设备/清缓存即丢失；且无法解决"后端是否继续跑"的根本问题 |
| **后端持久化管线快照 + 切回恢复（选定）** | 后端为单一事实源，管线后台续跑，切回任意设备可恢复；复用现有 session_store 持久化 |

## Affected Capabilities

| Capability | Change Type | Description |
|------------|-------------|-------------|
| `pipeline-events` | MODIFIED | 管线进度快照持久化到会话；后端不因客户端 SSE 断开而中断管线 |
| `frontend` | MODIFIED | 切换会话不再 abort 管线；selectSession 按会话状态恢复运行/完成的管线 UI |

## Success Criteria

- [ ] 管线运行中切换到其他会话，后端管线继续执行（日志/Langfuse 可验证），目标会话 status 保持 running 直至完成
  - > **适用范围**：当前仅 **fast path** 达成（PipelineRunner 后台线程保护）；ReAct 主链路降级为「快照恢复 + 轮询闭环」（design.md §8），完整后台化为后续 change。
- [ ] 切回运行中的会话：恢复分层时间轴，显示当前节点进度（各节点 status/耗时），运行节点正确高亮
- [ ] 切回已完成的会话：显示报告 + 已完成的静态分层时间轴（各节点真实耗时与摘要可回看）
- [ ] 管线后台完成后，切回会话能看到最终报告
- [ ] 既有会话恢复（report/chat_history）与 E2E 不回归

## Impact

- **代码**：`session_store.py`（管线快照字段读写）、`api.py`（管线运行期间写快照、SSE 断开后继续执行）、`agent_factory.py`（进度快照回调）、`frontend/src/App.tsx`（selectSession 恢复逻辑、条件化 abort）、`pipelineTree.ts`（layerTree 序列化/反序列化）
- **存储**：sessions 表新增 `pipeline_snapshot`（JSON）列（或复用 agent_process）
- **风险**：SSE 断开后 LangGraph 是否真继续执行需实测验证（若 harness 在客户端断开时取消生成器，需改为后台 task 执行管线 + SSE 仅订阅进度）
- **测试**：后端快照持久化单测、前端恢复逻辑单测、E2E 切换会话恢复管线用例
