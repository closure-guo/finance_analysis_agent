# Proposal: harden-llm-gateway-governance

## Why

add-llm-provider-gateway 已完成防腐层骨架与旧路径收口（resolver/registry/adapter/gateway/contracts/probes，5.1 全勾），但对照《LLM Provider Gateway 完整架构设计》，运行时治理层仍是缺口：probe 结果不缓存也不回写解析链（一次性按钮）；无 PolicyRouter 与 fallback 链执行（换 provider 韧性承诺未兑现）；ContextBudget 仍硬编码 120k 不按 capability 派生；前端不消费 capability 矩阵（弱能力 profile 仍可进深度模式）；evals judge 直连 litellm 阻止 `drop_params` 白名单化收紧。

## What Changes

- **probe 缓存与事实回写**：probe 结果缓存（键含 provider/model/base_url/key hash/litellm 版本，变更失效）；resolver 解析时合并 probe 事实与静态 capability（冲突以 probe 为准并记 warning，标 `probe_required`）；probe 事实经 `/api/llm-config/test` 写回前端。
- **PolicyRouter 与 fallback 链**：按 purpose/必需 capability/约束选 primary + fallback_chain（能力等价或更高才可入链）；OutputContract repair 耗尽与 ContentFiltered/不可重试错误按链切换 profile，全部 fallback 写 trace（`fallback_from`）；链长上限。
- **ContextBudget 按 capability 派生**：`harness/context.py` 的 120000 硬编码改为 `ModelProfile.capability.max_context` 派生；usage 真实值校准 + `usage_estimated` 标记。
- **前端 capability 门禁**：设置页展示能力矩阵（后端已返回）；`tool_call=false` 的 profile 禁用深度 ReAct 入口并显示原因；probe 完成后更新。**BREAKING**（交互行为）：弱能力 profile 的模式入口将被禁用。
- **judge 迁移 gateway + drop_params 白名单化**：evals judge 经 resolver/gateway 调用；随后移除全局 `litellm.drop_params=True`，adapter 白名单化参数发送，不支持的关键参数显式报错。

## Capabilities

- **New Capabilities**: `llm-policy-router`（profile 选择与 fallback 链）、`llm-budget-governance`（上下文/输出预算派生）、`llm-mode-gating`（前端模式入口门禁）
- **Modified Capabilities**: `llm-capability-probe`（增加缓存与事实回写）、`llm-provider-gateway`（resolver 合并 probe 事实；judge 纳入统一入口；drop_params 白名单化）

## Impact

- 代码：`src/finance_agent/llm/`（resolver/probes/新 router.py/registry）、`src/finance_agent/harness/context.py`、`evals/judges.py`、`src/finance_agent/api.py`（probe 写回）、`frontend/src/`（设置页 + 模式门禁）
- 风险：fallback 链引入故障路径复杂度（对策：链长上限 + 全链 trace）；drop_params 移除可能暴露隐藏参数不兼容（对策：合同测试 + 真实 nightly）；前端门禁改变用户可见行为（对策：禁用态显示原因与 probe 结果）
- 依赖：add-llm-provider-gateway 已收口（5.1 全勾）为基础；本 delta 不改动其已验收行为合同
