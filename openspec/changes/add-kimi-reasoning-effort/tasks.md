# add-kimi-reasoning-effort — Tasks

## 1. OpenSpec delta

- [x] proposal.md / design.md / tasks.md
- [x] specs/llm-provider-gateway delta（ADDED：kimi reasoning_effort 配置入口）
- [x] specs/llm-config delta（ADDED：Kimi 请求级 provider_options 白名单 + judge effort 配置入口）

## 2. 测试先行（TDD 红）

- [ ] registry：KimiOptions schema 校验（四档合法 / 未知值与未知 key 拒绝）
- [ ] resolver：请求级 kimi 模型 + provider_options 保留且校验通过；白名单外 key 显式报错；非 kimi/glm 模型不受影响
- [ ] adapter：`_provider_options_key` kimi/k3 识别；`apply_provider_options` 产出 `extra_body={"reasoning_effort": ...}`；deepseek/ark-glm 既有路径不回归
- [ ] judges：`JUDGE_REASONING_EFFORT` 非空并入 llm_config.provider_options；未设置不带该键

## 3. 实现（TDD 绿）

- [ ] registry.py：KimiOptions + PROVIDER_OPTIONS_SCHEMAS + REQUEST_OVERRIDABLE
- [ ] resolver.py：`_provider_options_from_request` kimi 族识别
- [ ] litellm_adapter.py：`_provider_options_key` + `apply_provider_options` kimi 分支
- [ ] evals/judges.py：JUDGE_REASONING_EFFORT 读取并入 llm_config

## 4. 验证

- [ ] 定向测试全绿（registry/resolver/adapter/judges）
- [ ] 宽回归（uv run pytest tests/llm tests/evals + 触及模块相关套件）无新增失败
- [ ] ruff + ruff-format 干净
- [ ] CI 全绿 + PR 合并
- [ ] （部署后）JUDGE_* 配 Kimi 实测：effort=none 请求成功 + temperature 接受性确认
