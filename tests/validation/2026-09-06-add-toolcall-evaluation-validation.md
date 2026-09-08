# 人工验证报告: add-toolcall-evaluation（Task 4.2 收尾）

**日期**: 2026-09-06
**验证人**: ZCode agent（真实 LLM quick 业务跑 + Langfuse 对账）
**关联 delta**: openspec/changes/add-toolcall-evaluation/
**前置**: 4.1 已勾；本报告覆盖最后一项 4.2（真实业务 quick 分析后核对 Langfuse tool_call:* span）

## 验证环境

- 后端真实模式（非 TESTING），quick 通道（AG-UI /api/agui/quick）
- LLM：阿里云 MaaS `openai/deepseek-v4-flash-0731`（自定义 baseUrl，经 llm_config 透传）
- 业务查询：「茅台最近有什么新闻？搜一下」（触发 web_search 工具）
- Langfuse 本地（docker compose 栈恢复后）

## 验证结果

| 验证项 | 预期行为 | 实际结果（Langfuse API 对账） | 通过 |
|---|---|---|---|
| tool_call:* span 出现 | 真实业务 quick 跑后 trace 含 tool_call span | `SPAN tool_call:web_search` ×2（两轮工具调用）+ `SPAN tool:web_search` 包装层 + `SPAN search_api_call` 底层 API span | ✅ |
| span output 可见 | tool_call span input/output 可判读 | 全部 output: yes（非 NULL） | ✅ |
| span 级别 | 无错误级事件 | 全部 level: DEFAULT | ✅ |
| agent 归属连带验证 | generation 以 agent 命名 | `GENERATION react_agent` ×2（两轮 ReAct），output 非空 | ✅ |

## 结论

- [x] 4.2 通过，可 archive（任务 8/8）
