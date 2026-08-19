# 人工验证报告: harden-llm-gateway-governance

**日期**: 2026-08-20
**验证人**: Closure（agent 执行，人工抽查项见下）
**关联 delta**: openspec/changes/harden-llm-gateway-governance/
**E2E 门禁**: tests/e2e/playwright/playwright-report（6 passed, 3.0m）

## 验证矩阵

| 验证项 | 依据 | 结果 |
|---|---|---|
| ProbeCache（五要素键/TTL/失效） | tests/llm/test_probe_cache.py | ✅ 全绿 |
| resolver 合并 probe 事实 + probe_required | tests/llm/test_resolver.py 增补 + tests/test_api_llm_config.py | ✅ probe 优先静态/未命中标记/保留 max_output 与 reasoning_* |
| PolicyRouter 选择 | tests/llm/test_router.py（12 用例） | ✅ 硬性过滤/等价链/链长≤2/quick 排序 |
| fallback 链执行器 | tests/llm/test_gateway_fallback.py | ✅ 五类错误切换/fallback_from/耗尽 re-raise/非链错误即传 |
| ContextBudget 派生 + 预算观测 | tests/llm/test_budget_governance.py | ✅ from_capability/calibrate/usage_estimated 接线/max_tokens_source/error_type |
| 前端矩阵+门禁 | frontend capabilityGating.test.ts（10 用例） | ✅ canEnterMode 语义/store 持久化 |
| 后端全量 | `pytest -k "not live"` | ✅ 1077 passed / 11 deselected |
| 前端 | `npm test` / `tsc -b` | ✅ 33 文件 303 tests / 类型干净 |
| **E2E 门禁（交互类）** | `tests/e2e/playwright` | ✅ 6 passed（streaming/管线/思考横幅全绿） |
| lint / 类型 | ruff 0；mypy 69 与基线一致（90 源文件） | ✅ |
| 真实 judge 链路 | `_call_judge_llm` 真调（JUDGE→LLM env 回退） | ✅ 精确返回 JSON |
| 真实 drop_params 关闭链路 | complete_text 方舟 GLM 真调（Task 8） | ✅ 成功输出 + temperature 白名单剔除落日志 |

## 人工抽查项（⬜ 待人工）

1. ⬜ 设置页 probe → 能力矩阵 UI 渲染 + 深度模式禁用态（tool_call=false profile 实机演练）
2. ⬜ Langfuse Dashboard：judge generation 按 `metadata.environment` 过滤可用（独立 client 已并为共享 client 的 metadata tag）
3. ⬜ evals 全量跑批对比基线（judge_failures=0 不回退）——本轮仅最小真调验证

## 已知边界 / follow-up（issue 化）

- judge 配置错误（IncompleteLLMConfigError）混入 `judge_parse_failed` 不区分（Medium，可观测性）
- fallback_from 只记最后一跳；resolver probe 缓存致部分测试 order-dependent（已用 pin 隔离）
- drop_params 白名单 warning 仅 logger 未挂 Langfuse trace；LLM_DROP_PARAMS_STRICT 开关须在首次调用前设置
- 前端：无 profile 用户探测后刷新丢 capability；「先显示静态 capability」落为「未探测提示」（sync 时 spec 措辞对齐）

## 结论

[x] 单测/集成/E2E 门禁/真实链路全部通过，可进入人工抽查后 sync + archive
[ ] 存在失败项，需修复后重新验证
