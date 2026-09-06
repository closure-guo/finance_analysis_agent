# ADR-0020: 开启 DeepSeek 原生思考模式（reasoning_content 一等公民化）

**Status**: Accepted  
**Date**: 2026-09-06  
**关联 delta**: enable-deepseek-thinking-mode；前置根因见 docs/incidents/017（reasoning 吃满配额）、018（provider 网关重构）

## Context

接入 DeepSeek 官方思考模式前，系统的「思考展示」是伪机制：从 `content` 里用 DSML 剥离逻辑切出思考段（`thinking_to_answer`），存在三个问题——用户看到的前端思考横幅不是模型真实推理；Langfuse trace 无 `reasoning_content`，无法观察真实思维链；DSML 剥离对格式脆弱（017 的截断/炸行事故链）。

当时禁用思考模式的注释基于旧版 DeepSeek API 限制（思考与工具调用不兼容）。2025-12 起官方文档明确支持思考模式下工具调用，唯一约束：**工具调用轮次的 assistant 消息在后续请求中必须回传 `reasoning_content`；非工具调用轮次可不回传（API 忽略）**。

流式形态：`reasoning_content`（思维链）与 `content`（最终回答）同级分离，先 reasoning delta 后 content delta。

## Decision

1. **开启思考模式，移除 disabled 配置**——思考不再是可选项，伪思考机制（DSML 剥离 + `thinking_to_answer`）随之退役。
2. **`LLMResponse` 新增 `reasoning_delta` 字段**——思维链与最终回答在流式协议上语义分离，不复用 `text_delta` 加标记。
3. **harness loop 事件来源调整**——`reasoning_delta` 直接驱动 `StreamEvent.think`，不再依赖 DSML 剥离产物。
4. **`Message` 新增 `reasoning_content`，工具调用轮次回传**——满足 API 约束的最小回传策略：仅工具调用轮次回传（非工具轮次 API 忽略，回传浪费 token）；`ContextManager.append_assistant` 同步接收。
5. **SSE 事件复用 `thinking_token` 承载 reasoning delta，新增 reasoning 完成标记**——前端 ThinkingBanner 渲染契约不变（消费端零改动），完成语义由显式标记替代 `thinking_to_answer` 剥离完成。
6. **`ReplyCollector` 直接收集 `reasoning_content` 落库**——落库思维链为真实推理原文，刷新恢复所见即模型所说。

**备选否决**：
- 保持禁用 + 伪思考——违背用户诉求（看真实推理），trace 无思维链；
- `text_delta` 携带 reasoning 加标记区分——破坏流式语义清晰性，harness 需解析标记；
- 保留 `thinking_to_answer` 兜底——reasoning 与 content 分离后剥离逻辑无意义；
- 所有轮次回传 reasoning_content——非工具轮次 API 忽略，纯浪费 token。

## Consequences

- 正面：前端思考横幅与 Langfuse trace 展示模型真实思维链；DSML 剥离路径退役，017 类截断炸行的触发面收窄；工具调用 + 思考模式官方支持（@live spec `deep-thinking-toolcall.spec.ts` 实测：澄清 ReAct 工具调用轮次 reasoning 正确回传、无 400）。
- 代价：`Message`/`LLMResponse`/上下文管理多一个字段的全链路维护；工具调用轮次必须回传 reasoning_content——漏回传即 400（历史故障），由 @live nightly（`deep-thinking-toolcall.spec.ts`）长期防回归。
- 边界：约束仅针对 DeepSeek 思考模式；其他 provider（如 GLM）经 gateway 适配层各自处理，不受本决策字段语义约束。

## References

- delta：enable-deepseek-thinking-mode（design.md 决策 1–6）
- 实现：`harness/llm_client.py`（reasoning_delta）、`harness/types.py` + `ContextManager`（reasoning_content 回传）、`harness/loop.py`（事件来源）、`api.py`（ReplyCollector）
- 长期验证：tests/e2e/playwright/tests/deep-thinking-toolcall.spec.ts（@live nightly）
