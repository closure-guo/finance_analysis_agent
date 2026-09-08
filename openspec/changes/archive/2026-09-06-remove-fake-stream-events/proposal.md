# Proposal: remove-fake-stream-events

## Why

流式通道存在三处系统冒充 LLM 的事件：① 时效性查询预搜索（api.py 伪 thinking_token + 伪 tool_call + 结果注入用户消息）、② 管线节点开始伪思考（`▶ 正在执行…`）、③ 节点完成摘要伪思考（`✓ …`）。用户无法区分模型真实推理与程序文案（transparent-system-events delta 的动因）。

原 transparent-system-events 方案（规则层 + system_note 事件类型 + 前端分层）已被更彻底且更便宜的方案取代：**直接删除**。前提已成立——DeepSeek 思考模式上线后（ADR-0020），真实 LLM 在时效性查询上会自行推理并调用 web_search（2026-09-06 实测：quick 模式模型自主推理「我需要搜索最新新闻」并两次调用 web_search）；管线节点进度已由分层时间轴 UI（node_start/node_complete）承载，thinking 旁路冗余。

## What Changes

- 删除 ①：`_run_react_analysis` 预搜索块（伪 thinking_token / 伪 tool_call / 手工 search_start/search_result / 搜索结果注入用户消息）
- 删除 ② ③：`_run_graph_streaming` 节点开始伪思考（`▶ …`）与节点完成摘要伪思考（`✓ …`），及 `_NODE_THINKING` 常量
- 固化不变量为 spec：chat-stream 新增「流式事件真实性」需求——LLM 事件通道 SHALL NOT 出现系统生成的 thinking_token/tool_call
- transparent-system-events delta 关闭（被本方案取代）

## Capabilities

- **New Capabilities**: 无
- **Modified Capabilities**: chat-stream（新增「流式事件真实性」需求）

## Impact

- 行为变化：时效性查询的搜索由 LLM 自行决定（真实推理 + 真实工具调用）；管线节点进度仅经管线事件/时间轴呈现，不再旁路 thinking_token；节点完成摘要不再注入思考横幅
- 回归风险点：quick 搜索横幅（由 agent 工具路径的 search_start 驱动，agent_factory 已实现，不依赖预搜索）；节点 LLM 真实 thinking 转发（custom mode，保留不动）
- 删除范围约 90 行，无新依赖
