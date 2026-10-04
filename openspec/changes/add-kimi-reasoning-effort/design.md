# add-kimi-reasoning-effort — Design

## 背景

judge 迁 Kimi（用户裁决 2026-10-04）遇到结构性缺口：Kimi Code 全系为思考模型，而 judge 以 temperature=0.0 高频调用。Kimi 文档给出的官方出口是 `reasoning_effort: none` → 关思考、路由 K2.8 Preview 无思考版。但本系统 provider_options 机制只登记了 deepseek / ark-glm 两族，Kimi 模型（openai/ 前缀）命中不了任何 schema，effort 无法透传。

## 决策

### D1：识别锚点用模型名，不用 provider 前缀

Kimi Code API 是 OpenAI 兼容端点，接入走 `openai/` 前缀（与方舟 GLM 同路径）。因此 ark-glm 先例的锚点策略延续：resolver `_provider_options_from_request` 与 adapter `_provider_options_key` 都以 **model 名**为识别锚点——`kimi` 子串（kimi-for-coding / kimi-for-coding-highspeed）或 `k3` 前缀（k3 / k3-256k）。风险与 ark-glm 相同（撞名可能性低：官方模型 ID 体系内 k3 段唯一）。

### D2：effort 走 extra_body，与 ark-glm 同机制

实证（registry 注释保留）：litellm openai 路由对顶层 `reasoning_effort` 判 UnsupportedParamsError 拒绝，extra_body 才透传到端点。Kimi 同为 openai/ 前缀 → `apply_provider_options` kimi 分支产出 `extra_body={"reasoning_effort": <值>}`。

### D3：schema 档位收 none/low/high/max 四档

Kimi 文档映射表还接受 medium/minimum/light/ultra/xhigh 等别名（服务端映射），本 schema 只收官方核心四档 + `none`（关思考），保持配置显式性；别名由配置者自行换算（medium→high 为文档推荐档）。extra="forbid" 拒绝未知 key。

### D4：不设默认值——不传 = 跟随 Kimi 模型默认

`DEFAULT_PROVIDER_OPTIONS` 不加 kimi 条目：env 分支不注入，只有显式配置（judge 的 JUDGE_REASONING_EFFORT、或请求级 provider_options）才携带。理由：Kimi 各模型默认档不同（k3=high、kimi-for-coding=max、highspeed=固定 ON），隐式默认会制造「配置了但值是猜的」的假象；不传 = 端点默认，语义最诚实。

### D5：JUDGE_REASONING_EFFORT 挂在 judges.py 请求级分支

judges.py 始终走 resolver 请求级分支（JUDGE_* 三件套 → llm_config），故 effort 以 `llm_config.provider_options` 形式并入，复用既有白名单校验链，不在 resolver 加 judge 专属 env 映射（避免 JUDGE_* 面继续膨胀）。未设置时不含该键。

## 口径影响（评估 SOP）

temperature=0.0 口径不变（代码继续发送）。effort=none 后 Kimi 无思考版对 temperature 的接受性待实测：接受 → 口径无损；拒收 → #216 降级兜底（丢 temperature 重试），需在 docs/evals/metrics.md 时间线记一行口径备注。
