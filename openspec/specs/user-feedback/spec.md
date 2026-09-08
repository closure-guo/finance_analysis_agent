# user-feedback Specification

## Purpose
TBD - created by archiving change add-user-feedback. Update Purpose after archive.
## Requirements
### Requirement: 用户反馈落 Langfuse trace

系统 SHALL 提供 `POST /api/feedback`，接收 `{ session_id, value }`（value ∈ `like` | `dislike`），将用户对 agent 输出的显式反馈落到「产生该输出的 Langfuse trace」上：like=1 / dislike=0，name=`user_feedback`，data_type=BOOLEAN。trace 解析 SHALL 由后端完成（按 session 关联的最近一次运行 trace）。端点 SHALL 满足旁路铁律：Langfuse 不可用 / trace 不存在 / 已过期时仅记 WARN，SHALL NOT 报 5xx；`session_id` 缺失或 `value` 非法 SHALL 返回 422。

#### Scenario: 点赞上报

- **WHEN** 前端对某条 agent 输出点击「点赞」
- **THEN** 系统 SHALL 解析该 session 最近一次运行的 `langfuse_trace_id`
- **AND** SHALL 调 `create_score(trace_id, name="user_feedback", value=1)`
- **AND** 前端保持选中态并标记已提交

#### Scenario: 点踩上报

- **WHEN** 点击「点踩」
- **THEN** SHALL 上报 value=0
- **AND** 点赞与点踩互斥（再次点击取消，可不上报取消）

#### Scenario: 参数校验

- **WHEN** `session_id` 缺失或 `value` 非 like/dislike
- **THEN** SHALL 返回 422

#### Scenario: Langfuse/trace 容错

- **GIVEN** Langfuse 不可达、trace 不存在或 session 无关联 trace
- **WHEN** 上报反馈
- **THEN** SHALL 记 WARN，响应仍为成功（前端不因后端失败报错）

### Requirement: 运行 trace 关联 session

系统 SHALL 在每次 chat 运行完成（quick AG-UI 与 deep ReAct）时，把该次运行的 `langfuse_trace_id` 关联到 session（持久化），供反馈端点解析。运行 span（react_obs）的 `trace_id` 为来源；无 Langfuse 或取不到时 SHALL 记 WARN 不阻断。历史 session 无关联 trace 时反馈端点 SHALL 按「无 trace」降级（仅前端本地 toggle，不报错）。

#### Scenario: quick 运行关联 trace

- **GIVEN** 一次 quick AG-UI 运行完成（react span 有 trace_id）
- **WHEN** 运行收尾
- **THEN** session SHALL 持久化该次运行的 `langfuse_trace_id`
- **AND** 覆盖同 session 上一次运行的关联（取最近一次）

#### Scenario: deep 运行关联 trace

- **WHEN** 深度分析（run_deep_analysis）完成
- **THEN** session SHALL 持久化该次运行的 trace_id（与 quick 同语义）

#### Scenario: 无 Langfuse 降级

- **GIVEN** 未配置 Langfuse 或取不到 trace_id
- **WHEN** 运行完成 / 上报反馈
- **THEN** 记 WARN，不阻断；前端反馈降级为本地 toggle

