# Tasks: harden-llm-gateway-governance

- [x] 1. ProbeCache：五项探测结果缓存（键 provider|model|base_url|api_key hash|litellm version；TTL；变更失效），TDD
- [x] 2. resolver 合并 probe 事实：命中缓存以 probe 覆盖 capability 冲突字段 + warning；未命中标 probe_required；`/api/llm-config/test` 探测后写缓存
- [x] 3. PolicyRouter 纯选择函数：purpose/硬性 capability 过滤/排序/fallback 链能力等价校验/链长上限/trace 选择字段，TDD
- [x] 4. fallback 链执行：OutputContract repair 耗尽与非重试错误（ContentFiltered/AuthError/ModelNotFound/UnsupportedCapability）依链切换 + fallback_from 落 trace + 总次数上限
- [x] 5. ContextBudget 按 capability.max_context 派生（去 120000 硬编码）+ usage 校准/usage_estimated 标记 + 观测补 error_type 与 max_tokens 派生来源
- [x] 6. 前端能力矩阵展示 + 模式入口门禁（tool_call=false 禁深度 ReAct、json_output=false 禁管线入口；显示原因；probe 优先静态；probe 未完成不误伤）
- [x] 7. judge 迁移 gateway（purpose=judge 走 resolver/complete_text，保持 JUDGE_* 独立映射与 environment 审计），evals 合同测试随迁
- [x] 8. drop_params 白名单化：移除全局 drop_params=True，adapter 参数白名单 + 不支持关键参数显式报错；nightly 真实合同探测验证无隐藏依赖（可单开关回滚）
- [x] 9. 全量验证（pytest/ruff/mypy/E2E 门禁——task 6 交互类适用）+ 真实跑批 evals 对比基线 + 人工验证报告落 tests/validation/
