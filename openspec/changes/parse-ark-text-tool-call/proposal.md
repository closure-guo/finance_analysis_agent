# Proposal: parse-ark-text-tool-call

## Why

方舟 GLM 在部分轮次把工具调用以原生文本格式
`<tool_call>NAME<arg_key>K</arg_key><arg_value>V</arg_value></tool_call>`
输出在 content 里（而非 OpenAI 结构化 tool_calls 字段）。harness 不识别该
格式时整段 XML 作为最终回答流给用户、意图中的工具调用不会执行——线上
601700 深研超时后 Agent 想重试管线，用户只看到一段原始 XML 文本
（incidents 018 方舟兼容家族 / 020 复盘）。

## What Changes

harness LLM 客户端（`litellm_client.chat_stream`）在流式 text 增量中识别
上述文本格式工具调用：完整块转为结构化 `ToolCallRequest` 下发执行，
块文本不进入正文；正常正文下发延迟不超过标签前缀长度；未闭合块流结束
时原样作为正文返回（不吞内容）。

## Capabilities

- **New Capabilities**: `llm-tool-call-compat`（LLM 工具调用的 provider 兼容）
- **Modified Capabilities**: 无

## Impact

- 新增 `src/finance_agent/harness/ark_tool_call_text.py`（流式识别过滤器）
- `src/finance_agent/harness/litellm_client.py` chat_stream 接线
- 纯后端 LLM 客户端内行为，不改 SSE 协议与前端
