# 人工验证报告: add-llm-api-form

**日期**: 2026-08-28
**验证人**: Closure（agent 执行验证 + 抽查）
**关联 delta**: openspec/changes/add-llm-api-form/
**变更性质**: 前端设置面板 UI（下拉框）+ 后端透传，交互类变更

## 目标

设置面板新增 API 形式下拉（chat_completion / messages / responses），裸模型名前缀推导，缺省 OpenAI Chat Completion。

## 验证矩阵

| 验证项 | 依据 | 结果 |
|---|---|---|
| 后端 apiForm 字段与校验 | `api.py:183` `LLMConfigRequest.apiForm` + `:185-190` 校验器非法值 422；`_to_llm_config:251` 透传；`llm/config.py:27` | ✅ |
| adapter 三种 API 形式映射 | `litellm_adapter.py:473-477` `_API_FORM_TO_LITELLM_API`；`apply_api_form_kwargs:480-487`；gateway 三入口 + fallback 均消费（`gateway.py:259,489,610,943`） | ✅ |
| 前端下拉框 | `App.tsx:1949,2114`；`llmConfig.ts:12,82,111-119` 字段 + 预设携带 apiForm | ✅ |
| 裸模型名前缀推导 | `llmConfig.ts:222-223`；`:180` payload 只带合法值 | ✅ |
| 后端测试 | `tests/test_llm_config.py` + `tests/llm/test_resolver.py` + `tests/llm/adapters/test_apply_provider_options.py` | ✅ 通过 |
| 前端测试 | `frontend/src/test/llmConfig.test.ts`（54 tests） | ✅ 54 passed |
| spec↔代码契约 | llm-config 主规范「apiForm」requirement 与后端/前端实现一致 | ✅ |
| `openspec validate add-llm-api-form --strict` | — | ✅ 通过 |

## 人工抽查项（⬜ 待真实环境 follow-up）

1. ⬜ 浏览器实机：设置面板下拉渲染 + 切换后模型名输入正确触发前缀推导（本轮以 54 前端单测为自动化证据）

## 已知边界 / follow-up

- 无

## 结论

[x] 自动化验证全部通过（后端 + 前端测试套件 + 契约），可 sync + archive；浏览器实机项已在「人工抽查项」登记为 follow-up
[ ] 存在失败项，需修复后重新验证
