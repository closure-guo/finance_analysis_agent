# Design: update-temperature-degrade-fallback

## Approach

在 `litellm_adapter` 三个 raw 入口（`raw_completion` / `raw_stream` / `raw_acompletion`）统一包一层降级：捕获首次调用异常 → `str(err)` 含 `temperature` 且 kwargs 带 `temperature` → 剔除后原参重试一次 + `update_current_span` 记 degradation + logger warning。选 adapter 而非 gateway 三入口：一处覆盖 gateway 全部调用方（complete_text/complete_stream/complete_stream_async）、capability probe 与 evals judge，且不动 gateway 各自的重试/续写控制流。

## Alternatives Considered

- **设置页加 temperature 配置项（用户提议）**：把 provider 能力限制推给用户；不覆盖管线硬编码基线（0.3 是 deep 合约参数，非用户配置）与 evals 跑批；每换一个思考型模型都要用户知道去改。拒绝为主方案；若将来需要人为控温，可作 provider_options 请求级白名单 key 单独立项。
- **模型名启发式预剔除**（kimi-k2-thinking 等 → 不发 temperature，类比 ark-glm thinking_forced）：需要维护名字清单，新模型上线即失效；运行时降级对任意 provider 自动生效。拒绝。
- **gateway 三入口各自改重试**：三处重复 + 动各入口复杂控制流（重试循环/续写/finalize）。拒绝。

## Risks

- 错误文本匹配依赖 `temperature` 子串：误报面窄（含该词的错误几乎必为参数拒绝），且误报后果仅一次无害重试；不匹配则维持现状（显式报错）。
- 降级后模型走端点默认温度（思考型=1）：对输出风格的控制力下降，但这是端点硬约束，非本方案引入。
- 流式请求的 400 在 litellm 发起请求时抛出，try/except 在调用点即可捕获，无半流重放问题。
