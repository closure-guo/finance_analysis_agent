# 复测记录: fix-capability-probe-tool-call（真实 Kimi 端点）

**日期**: 2026-10-05
**验证人**: ZCode（owner 委托执行）
**关联 delta**: openspec/changes/fix-capability-probe-tool-call/
**前置报告**: tests/validation/2026-10-03-fix-capability-probe-tool-call-validation.md（自动化部分）

## §4 逐项复测结果（对运行中容器 API 实测）

1. **真实 Kimi 端点复测** ✅
   - POST /api/llm-config/test（openai/kimi-for-coding @ https://api.kimi.com/coding/v1，key 取自 JUDGE_API_KEY）：
     `success=true`，五项能力 **non_stream/stream/tool_call/tool_followup/json_output 全 true**，warnings=["latency=slow"]，10431ms
   - 工具调用 ✓：模型主动调用工具，无需触发「模型未主动调用工具，强制指定后通过」回退警告（该路径由两级判定单测覆盖）
   - 模型自动发现：POST /api/llm-config/models → `["k3","k3-256k","kimi-for-coding","kimi-for-coding-highspeed"]`；裸名 → `openai/<model>` 前缀推导由已合并前端单测覆盖（buildModelWithPrefix kimi/foo.bar 两例）
2. **深度模式解锁** ✅
   - probe 缓存随 2026-10-05 06:43 容器重建清空；设置中心现行 glm-5.3 thinking=enabled
   - 真实深度分析（600519）completed（关联 tests/validation/2026-10-05-update-temperature-degrade-fallback-validation.md），/api/analyze 无 capability.tools=none 拒绝
3. **未测态目视** ⚠️ 单测级验证
   - 真实端点未复现 tool_call=false 样本：kimi-for-coding / glm-5.3 / glm-4-flash 三模型探测均全通过，无现成「不跟随工具」provider
   - 灰「未测」语义与渲染由已合并前端单测覆盖（capabilityItemState / formatProbeWarning 共 5 例；前端 643 passed）；后端两级判定「端点拒收 tools → None + warning」代码路径核对无误
4. **前缀非法路径** ✅
   - model=`kimi/xxx` + 自定义 baseUrl → HTTP 200 + `errorType=model_prefix_invalid` + 文案「未知 provider 前缀 'kimi'。已知: ['anthropic','deepseek','gemini','openai']；OpenAI 兼容端点请使用 openai/<model>」（非 500 裸栈）

## 结论

- [x] 真实 Kimi 端点复测通过（1/2/4 实测 ✅，3 为单测级验证 ⚠️），可 archive
