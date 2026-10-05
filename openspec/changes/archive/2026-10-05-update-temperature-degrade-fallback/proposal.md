# Proposal: update-temperature-degrade-fallback

## Why

深度管线按 gateway 合约基线硬编码 `temperature=0.3`（`_llm_utils.py:688`、`report.py:335`）；思考型模型端点（如 Kimi kimi-k2-thinking 系）**只允许 temperature=1**，首调即 400 `invalid temperature: only 1 is allowed for this model`——PR #215 部署后工具调用探测/守卫已通，深度分析死在真实调用首步。温度限制是 provider 能力事实，应系统消化而非要求用户在设置页手动配温度（用户提议的 UI 配置项不覆盖 evals/管线硬编码基线，且把 provider 怪癖推给用户）。

## What Changes

- adapter 三个 raw 入口（`raw_completion` / `raw_stream` / `raw_acompletion`）增加**温度拒绝自动降级**：请求携带 `temperature` 且调用异常信息含 temperature 时，剔除 temperature 后**重试一次**（端点默认值即 1），经 `update_current_span` 记 `degradation=temperature_dropped_endpoint_rejected` + logger warning
- 仅重试一次；降级后仍失败按原错误归一上抛；不携带 temperature 的请求不受影响
- 一处收口覆盖全部调用方：gateway 三入口、probes、evals judge

## Capabilities

- **New Capabilities**: 无
- **Modified Capabilities**:
  - `llm-provider-gateway`：litellm 适配收口新增「temperature 拒绝自动降级」需求（ADDED requirement）

## Impact

- 后端：`src/finance_agent/llm/adapters/litellm_adapter.py`（三个 raw 入口 + 判定 helper）
- 测试：`tests/llm/adapters/test_litellm_adapter.py`
- 不改 gateway 控制流、不改前端、不改请求契约
