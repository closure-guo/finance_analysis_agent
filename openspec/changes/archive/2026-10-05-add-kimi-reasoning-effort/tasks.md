# add-kimi-reasoning-effort — Tasks

## 1. OpenSpec delta

- [x] proposal.md / design.md / tasks.md
- [x] specs/llm-provider-gateway delta（ADDED：kimi reasoning_effort 配置入口）
- [x] specs/llm-config delta（ADDED：Kimi 请求级 provider_options 白名单 + judge effort 配置入口）

## 2. 测试先行（TDD 红）

- [x] registry：KimiOptions schema 校验（四档合法 / 未知值与未知 key 拒绝）——tests/llm 用例绿（宽回归 1615 passed）
- [x] resolver：请求级 kimi 模型 + provider_options 保留且校验通过；白名单外 key 显式报错；非 kimi/glm 模型不受影响——tests/llm 绿
- [x] adapter：`_provider_options_key` kimi/k3 识别；`apply_provider_options` 产出 `extra_body={"reasoning_effort": ...}`；deepseek/ark-glm 既有路径不回归——tests/llm/adapters 绿
- [x] judges：`JUDGE_REASONING_EFFORT` 非空并入 llm_config.provider_options；未设置不带该键——tests/evals 绿

## 3. 实现（TDD 绿）

- [x] registry.py：KimiOptions + PROVIDER_OPTIONS_SCHEMAS + REQUEST_OVERRIDABLE——src/finance_agent/llm/registry.py:45/61/76 工件核对
- [x] resolver.py：`_provider_options_from_request` kimi 族识别——src/finance_agent/llm/resolver.py:109-110
- [x] litellm_adapter.py：`_provider_options_key` + `apply_provider_options` kimi 分支——src/finance_agent/llm/adapters/litellm_adapter.py:407/452-459
- [x] evals/judges.py：JUDGE_REASONING_EFFORT 读取并入 llm_config——evals/judges.py:252-254

## 4. 验证

- [x] 定向测试全绿（registry/resolver/adapter/judges）——uv run pytest tests/llm tests/evals tests/test_api_llm_config.py
- [x] 宽回归（uv run pytest tests/llm tests/evals + 触及模块相关套件）无新增失败——1615 passed / 5 skipped / 1 failed（唯一失败 test_fm_decision_live 为 @live Langfuse 真数据用例：单跑即 skip，#213 全量跑同款记录，与本 delta 无关）
- [x] ruff + ruff-format 干净——All checks passed / 619 files already formatted
- [x] kimi effort 显式配置时 suppress_temperature（端点温度锁死实证，红→绿）
- [x] CI 全绿 + PR 合并
- [x] （部署后）JUDGE_* 配 Kimi 实测：effort=none 请求成功 + 温度锁死实证（思考档=1/无思考档=0.6，suppress 契约吸收）
- [x] 容器内 judge 链端到端验证 + metrics.md 口径备注——metrics.md「judge 端点切换切点(2026-10-04)」备注在案；#219 容器实测 effort=none 成功+温度锁死(1/0.6)；本日容器端 /api/llm-config/test 对 kimi-for-coding 能力 5/5 ✓
