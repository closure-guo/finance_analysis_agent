# 人工验证报告: add-context-length-config

**日期**: 2026-08-28（重写；原 2026-08-20 报告引用的测试不存在，判定失实后按真实实现重写）
**验证人**: Closure（agent 执行 TDD + 验证）
**关联 delta**: openspec/changes/add-context-length-config/
**变更性质**: 纯后端配置透传 + 前端设置输入（交互类）

> **修订说明**：原 `2026-08-20-add-context-length-config-validation.md` 声称的测试（`tests/llm/test_provider_options.py::TestContextLengthOverride`、`tests/test_api_llm_config.py` contextLength 用例、前端 llmConfig.test.ts contextLength 用例、E2E 11 passed）在当时并不存在——功能从未落地（全库 grep `contextLength` 零命中，含引入提交 `0fa8099` 时）。本轮按 delta 契约以 TDD 补齐实现与测试后重写本报告。

## 目标

用户经前端设置页配置上下文长度（tokens），随请求级 `llm_config.contextLength` 下发；resolver 解析 profile 时请求级值覆盖 `capability.max_context`，无请求级值时 `LLM_MAX_CONTEXT` env 覆盖默认；非法值显式报配置错误；留空跟随 registry 静态默认。

## 验证矩阵

| 验证项 | 依据 | 结果 |
|---|---|---|
| 请求级覆盖 | `llm/resolver.py::_apply_context_length_override`（dataclasses.replace 覆盖 capability.max_context）；`tests/llm/test_resolver.py::TestContextLengthOverride::test_request_override_max_context` | ✅ max_context=200000，其余能力字段不变 |
| 环境变量覆盖 | resolver 读 `LLM_MAX_CONTEXT`（无请求级值时）；`test_env_override_when_no_request_value` | ✅ 300000 生效 |
| 请求优先于 env | `test_request_takes_priority_over_env` | ✅ 请求 200000 优先于 env 300000 |
| 非法值拒绝 | `api.py::LLMConfigRequest.contextLength` field_validator（≤0 → 422）；resolver `_parse_context_length`（非正整数 → IncompleteLLMConfigError）；`test_llm_config_request_rejects_non_positive_context_length` + `test_invalid_request_value_raises` + `test_invalid_env_value_raises` | ✅ 0/-5/1.5/"abc" 均拒绝 |
| 留空跟随默认 | `test_empty_follows_registry_default` | ✅ openai-compatible 静态 128000 |
| 全链透传 | `LLMConfigRequest.contextLength` → `_to_llm_config` → `LLMConfig.contextLength` → `_request_config_dict`（`_llm_utils.py`/`report.py`）→ gateway `resolve_profile(llm_config=...)` | ✅ 链路打通（`test_llm_config_dataclass_carries_context_length`） |
| 前端载荷 | `frontend/src/llmConfig.ts::buildLlmConfigPayload` 仅正整数携带 contextLength；`frontend/src/test/llmConfig.test.ts` 2 用例 | ✅ 全绿（56 passed） |
| 前端设置输入 | `App.tsx` SettingsModal 上下文长度 number 输入（min=1），保存仅含正整数；`npx tsc -b` 干净 | ✅ |
| 后端回归 | `tests/test_llm_config.py` + `tests/llm/test_resolver.py` + `tests/test_pipeline_llm_config.py` + `tests/test_api_llm_config.py` + `tests/test_llm.py` + `tests/nodes/test_call_llm_streaming_gateway.py` + `tests/llm/test_gateway_resume.py` + `tests/llm/test_types.py` | ✅ 194 passed（96 + 98 两批） |
| 前端全量 | `npx vitest run` | ✅ 37 文件 333 passed |
| `openspec validate add-context-length-config --strict` | — | ✅ 通过 |

## 人工抽查项（⬜ 待真实环境 follow-up）

1. ⬜ 浏览器实机：设置面板输入 contextLength → 保存 → 深度分析，确认 ReAct 上下文预算（`ContextBudget.from_capability`）反映覆盖值
2. ⬜ 真实 LLM：长上下文请求实际放行（非因 max_context 截断）

## 已知边界 / follow-up

- 请求级 contextLength 仅随请求级 model/baseUrl 一并生效（`_request_config_dict` 无 model 时返回 None，回退 env/preset——此时由 `LLM_MAX_CONTEXT` 兜底）
- 前端对 0/负/非整数输入按「未设置」处理（不发送），后端直接 API 调用仍 422 拦截

## 结论

[x] 实现 + TDD 测试 + 回归全部通过，可 sync + archive；真实环境抽查项已登记为 follow-up
[ ] 存在失败项，需修复后重新验证
