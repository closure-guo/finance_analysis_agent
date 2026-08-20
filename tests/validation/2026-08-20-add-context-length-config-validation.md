# 人工验证报告: add-context-length-config

**日期**: 2026-08-20
**验证人**: Closure（agent 执行，人工抽查项见下）
**关联 delta**: openspec/changes/add-context-length-config/
**E2E 门禁**: tests/e2e/playwright/playwright-report（11 passed, 1.8m）

## 验证矩阵

| 验证项 | 依据 | 结果 |
|---|---|---|
| resolver 请求级 contextLength 覆盖 | tests/llm/test_provider_options.py::TestContextLengthOverride | ✅ max_context=200000、其余能力不变、非法值拒绝 |
| 环境 LLM_MAX_CONTEXT 覆盖 | 同上 | ✅ |
| api LLMConfigRequest 校验 + _to_llm_config 透传 | tests/test_api_llm_config.py | ✅ 正整数 Pydantic 校验(0/负数→422) |
| legacy 壳透传 | tests/test_llm.py 相关 | ✅ 31/32 targeted |
| 前端 payload + 输入 | frontend llmConfig.test.ts（contextLength 用例）+ SettingsModal | ✅ 306 tests / tsc 0 |
| 后端全量 | pytest -k "not live" | ✅ 1088 passed / 11 deselected |
| lint / 类型 | ruff 0；mypy 68（净降于基线 69） | ✅ |
| E2E 门禁（交互类） | tests/e2e/playwright | ✅ 11 passed |

## 人工抽查项（⬜ 待人工）

1. ⬜ 设置页填入 contextLength（如 200000）→ 保存 → 设置页重新打开值保留；刷新后仍在
2. ⬜ 深度分析发起 → 若该模型真实上下文大于默认，ReAct 不再早期压缩（可在 Langfuse 观察 history 长度/无过早 compaction）

## 说明

- 语义对齐 ZCode per-model `limit.context`：留空跟随 registry 静态 max_context 默认；填正整数覆盖。不做模型上限探测（follow-up）。
- 非法值（≤0）前端省略不发送 + 后端 Pydantic 422，双保险。

## 结论

[x] 单测/集成/E2E 门禁全部通过，可进入人工抽查后 sync + archive
[ ] 存在失败项，需修复后重新验证
