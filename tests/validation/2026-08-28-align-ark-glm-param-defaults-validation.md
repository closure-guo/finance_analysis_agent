# 人工验证报告: align-ark-glm-param-defaults

**日期**: 2026-08-28
**验证人**: Closure（agent 执行验证 + 抽查）
**关联 delta**: openspec/changes/align-ark-glm-param-defaults/
**变更性质**: 纯后端配置对齐（非交互类，不适用 E2E 浏览器门禁）

## 目标

ark-glm 的 `max_tokens` 对齐官方默认 65536；`reasoning_effort` 提供显式配置入口（请求级 → env → registry 默认 max）。

## 验证矩阵

| 验证项 | 依据 | 结果 |
|---|---|---|
| ark-glm max_tokens 默认 65536 | `llm/registry.py:32-42` `ArkGLMOptions(max/high/low, extra=forbid)`；`:48/54/60` 三表注册 ark-glm；`:123,125` `max_output=65536` + `default_params={"max_tokens": 65536}` | ✅ |
| reasoning_effort 请求级透传 | `llm/adapters/litellm_adapter.py:449-454` ark-glm 分支产出 `extra_body={"reasoning_effort":...}` | ✅ |
| reasoning_effort env 兜底 | `llm/resolver.py:137-142` env 分支识别 `glm` → `LLM_REASONING_EFFORT` 覆盖；`:104-106` 请求级白名单 | ✅ |
| 后端测试 | `tests/llm/test_provider_options.py` + `tests/llm/adapters/test_apply_provider_options.py` | ✅ 通过（含 provider_options 断言） |
| spec↔代码契约 | llm-provider-gateway 主规范「关键参数不静默丢弃」「非关键参数白名单」requirement 与 adapter/resolver 实现一致 | ✅ |
| `openspec validate align-ark-glm-param-defaults --strict` | — | ✅ 通过 |

## 人工抽查项（⬜ 待真实环境 follow-up）

1. ⬜ 真实方舟 GLM 调用：确认真实响应 max_tokens=65536 生效、`reasoning_effort` 被 provider 接受（本轮以测试套件 75 passed + 代码契约为自动化证据）

## 已知边界 / follow-up

- 无

## 结论

[x] 自动化验证全部通过（测试套件 + 契约），可 sync + archive；真实 provider 调用项已在「人工抽查项」登记为 follow-up
[ ] 存在失败项，需修复后重新验证
