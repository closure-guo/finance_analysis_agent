# add-kimi-reasoning-effort

## Why

2026-10-04 评估裁判（judge）从方舟 deepseek-v4-flash 迁移到 Kimi Code API（用户裁决：管线主 LLM 切 bigmodel GLM-5.3，judge 切 Kimi 以与被评模型解耦）。Kimi Code 文档确认其 4 个模型 ID（k3 / k3-256k / kimi-for-coding / kimi-for-coding-highspeed）**全部是思考模型**（effort 三档 low/high/max，无官方非思考档），但文档同时给出出口：`reasoning_effort: none` 会关闭思考并路由到「K2.8 Preview 无思考版」。

judge 链路以 temperature=0.0 为口径（采样确定性），且逐 trace 高频调用。若直接切 Kimi 不传 effort：K2.8 默认 effort=max（逐调用深度思考），评估耗时与套餐 token 消耗失控；思考模式下端点拒收 temperature≠1，#216 降级重试虽可兜底，但 judge 采样口径被迫漂移。因此必须给 judge 一条「关思考」的显式配置通道。

现状缺口：Kimi 模型族（openai/ 前缀 + model 含 kimi/k3）在 resolver/adapter 的 provider_options 白名单与 schema 中无登记——`_provider_options_key` 返回 None，effort 配置无法透传。

## What Changes

- registry 新增 `KimiOptions` schema：`reasoning_effort: none/low/high/max`（`none`=关思考，路由 K2.8 无思考版；Kimi 文档映射表 medium→high，本 schema 只收官方核心四档，保持显式性），extra="forbid"
- resolver 请求级白名单 `REQUEST_OVERRIDABLE["kimi"] = {"reasoning_effort"}`；模型族识别锚点：model 含 `kimi` 或 `k3/` 段（openai/ 前缀下）
- adapter `_provider_options_key` 同锚点识别 kimi 族；`apply_provider_options` 对 kimi 产出 `extra_body={"reasoning_effort": <值>}`（与 ark-glm 同机制：litellm openai 路由拒收顶层 reasoning_effort）
- judges.py 新增环境变量 `JUDGE_REASONING_EFFORT`：非空时并入 llm_config.provider_options，请求级透传；未设置时不传（跟随 Kimi 模型默认档），不新增隐式默认
- adapter 对 kimi 在 effort 显式配置时产出 `suppress_temperature=True`（内部契约）：Kimi 端点采样温度锁死（实证 2026-10-04——思考档仅接受 temperature=1、无思考档仅接受 0.6），temperature 一律不发送，采样跟随端点固定值

## Impact

- Affected specs: llm-provider-gateway（adapter 消费 + 透传机制）、llm-config（请求级白名单 + judge effort 配置入口）
- Affected code: src/finance_agent/llm/registry.py、src/finance_agent/llm/resolver.py、src/finance_agent/llm/adapters/litellm_adapter.py、evals/judges.py
- 不影响主管线（glm 族路径零改动）。**judge 采样口径变化（实测后确认）**：Kimi Code 端点温度完全锁死，temperature=0.0 无法实现——kimi 请求不再发送 temperature，采样=端点固定值（无思考 K2.8 为 0.6）；judge 采样确定性较 temperature=0.0 弱化，已在 docs/evals/metrics.md 记口径备注。#216 温度降级重试保留为兜底（kimi 未配置 effort 的请求仍会先 400 再降级）
