# Design: harden-llm-gateway-governance

## Approach

五个子域按依赖顺序推进，共享「probe 事实」这一新事实源：

1. **probe 缓存**（`llm/probes.py` 内加 `ProbeCache`，进程内 TTL + 键哈希）：键 = sha256(provider|model|base_url|api_key|litellm_version)。先做缓存，因为 router 与门禁都消费 probe 事实。
2. **resolver 合并 probe 事实**：resolve_profile 完成静态解析后，查 ProbeCache 命中则以 probe 覆盖 capability 冲突字段（记 warning 到 profile 元数据）；未命中标 `probe_required`。不做解析期主动探测（避免每次调用加延迟），事实由设置页/nightly probe 写入缓存。
3. **PolicyRouter**（新 `llm/router.py`）：纯函数 `select(purpose, required_capability, constraints, candidates) -> (primary, chain)`；fallback 执行器放 gateway（OutputContract 耗尽与非重试错误钩子处），链长上限 2，切换写 `fallback_from`。
4. **ContextBudget 派生**：harness/context.py 接收可选 capability.max_context（默认回落 registry 中性值）；usage 校准 + estimated 标记；观测补 error_type/派生来源。
5. **前端门禁 + judge 迁移 + drop_params**：前端消费既有 `/api/llm-config/test` 矩阵（后端已就绪）；judge 改走 `complete_text(purpose="judge")`；全链迁完后移除 `drop_params=True`，合同测试 + 真实 nightly 验证无隐藏依赖。

## Alternatives Considered

- fallback 执行放 PolicyRouter 内：否——router 保持纯选择逻辑，执行属 gateway IO 层，便于单测。
- 解析期主动 probe：否——每次 resolve 引入真实调用延迟；改为「缓存事实被动合并 + 设置页主动探测」。
- drop_params 先收再修：否——先迁 judge 与合同测试锁定参数面，再一次性移除，避免中间态半静默。

## Risks

- probe 缓存失效遗漏（模型热切换）：键含全部四要素 + litellm 版本，nightly 复测兜底。
- fallback 引入新故障路径：链长上限 + 全链 trace + 合同测试覆盖切换语义。
- 前端门禁误伤（probe 偶发失败）：门禁只看「probe 明确失败」，缓存未命中/超时不触发禁用（保守放行 + 提示重测）。
- drop_params 移除暴露未知不兼容：真实 nightly 合同探测 + 可回滚（单开关还原）。
