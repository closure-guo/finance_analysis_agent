## Why

F2（已归档）建立了 E2E 门禁基础设施：`npx playwright test` 能拉起前后端并跑绿 smoke。但门禁对**交互类变更**尚未真正生效--只有 smoke.spec（验证页面可达），没有 streaming/contract/interaction spec（验证流式渲染、网络契约、交互状态）。当交互类变更进站时，Step 4.5 门禁无 spec 可跑，仍只能沿用人工验证。

本变更（F3a）补齐核心 spec 并落地 LLM stub，使门禁对交互类变更完全生效。F3b（独立 delta）处理 @live 套件迁移。

> 上游设计文档：`docs/superpowers/specs/2026-07-26-e2e-workflow-integration-design.md` §5 F3 阶段

## What Changes

- 后端实现 LLM stub（替换 F2 的 `return None` 占位）：TESTING=1 时 LLM 客户端按固定节奏吐文本 delta，让流式断言是确定性的。**F3a stub 只支持快速模式**（ReAct Agent 返回纯文本，不触发 tool_call，1 轮完成）；深度模式完整 stub 推迟到 F3b @live 套件（5 层管线各节点 stub 复杂度高，且 @live 真 LLM 链路已覆盖深度模式）
- 前端添加 `data-testid` 属性到关键交互元素（stream-output / stream-status / stream-error / retry-button / send-button），作为 E2E spec 的稳定断言锚点（不改行为，只加属性）
- 新增 `tests/e2e/playwright/tests/streaming.spec.ts`：3 场景（正常流式增量渲染 + 指示器生命周期 + 中断恢复）--基于快速模式
- 新增 `tests/e2e/playwright/tests/contract.spec.ts`：1 场景（点击发送发出正确 POST /api/chat 请求并收到 SSE）
- 新增 `tests/e2e/playwright/tests/interaction.spec.ts`：1 场景（发送中按钮禁用并变色）

## Capabilities

### New Capabilities

- `e2e-core-specs`: E2E 核心测试套件的行为契约--streaming/contract/interaction 三个 spec 应验证的交互行为

### Modified Capabilities

- `e2e-infrastructure`: MODIFIED Requirement `Testing Mode Switch`--TESTING=1 下 LLM 客户端替换为可控 stub（替换 F2 的占位 return None）

## Impact

| 范围 | 影响 |
|---|---|
| 后端 `src/finance_agent/agent_factory.py` | `_make_llm_client` 的 TESTING 分支替换为 stub 客户端实现 |
| 新增 `src/finance_agent/harness/stub_llm_client.py` | stub LLM 客户端，按固定节奏吐 LLMResponse（纯文本，不触发 tool_call） |
| 前端 `frontend/src/App.tsx` | 关键元素加 `data-testid` 属性（不改行为） |
| 新增 `tests/e2e/playwright/tests/streaming.spec.ts` | 3 场景 |
| 新增 `tests/e2e/playwright/tests/contract.spec.ts` | 1 场景 |
| 新增 `tests/e2e/playwright/tests/interaction.spec.ts` | 1 场景 |

依赖：F2（已完成）的 TESTING 开关、`/api/test/seed` 骨架、Playwright 项目骨架。
