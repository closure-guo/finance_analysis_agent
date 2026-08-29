# Proposal: truncation-escalate-resume

## Why

管线节点的截断升级重试（`call_llm_streaming` 收到 OutputTruncatedError 后
`max_tokens` 翻倍至 131072 重试）目前用**原始 messages 从头重跑**整个生成。
汉森制药 002412 复盘（2026-08-26）：technical_analyst 首跑 17 分钟产出
65536+ 部分正文后截断，升级重试从头再生成 34 分钟并以未归类错误失败——
51 分钟全烧在重复劳动上，且首跑的部分正文（完整 JSON 开头）被丢弃。
gateway 内的续写（resume）机制已存在（`build_resume_kwargs`：携带已生成
正文尾部 + 剩余配额），但升级层没有复用它。

## What Changes

截断升级重试 SHALL 以续写方式进行：携带首轮已生成正文（尾部注入 +
续写指令）与翻倍预算下的剩余配额，不重发原始问题从头生成。两次截断
仍失败 SHALL 维持既有语义（上抛 OutputTruncatedError）。非截断错误的
重试语义不变（不翻倍、不续写）。

## Capabilities

- **New Capabilities**: `llm-truncation-escalation`（截断升级重试策略）
- **Modified Capabilities**: 无（主规范库无既有条目，行为此前仅存在于
  incidents 019 与调用方测试）

## Impact

- `src/finance_agent/nodes/_llm_utils.py` call_llm_streaming 升级分支改用
  `build_resume_kwargs` 构造续写请求，累积拼接两轮正文返回
- 纯后端 LLM 调用层，不改 SSE 协议与前端
