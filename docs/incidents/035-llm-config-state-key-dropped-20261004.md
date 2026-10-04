# Incident 035: llm_config 未声明被图静默丢弃——请求级模型配置在管线整条哑火

**日期**: 2026-10-04
**状态**: 已修复
**关联**: [027（同族根因）](027-price-validate-state-keys-dropped-20260913.md)、PR #215/#216（前置修复：能力探测假阴性、temperature 降级）

## 症状

用户在前端配置 Kimi（`openai/k3-256k`）后跑深度分析，会话 `failed`，
`failure_reason = InvalidSubscription: Your account (2108484499) does not have
a valid AgentPlan subscription`（方舟 plan 端点，`.env` 回退配置指向的端点，
套餐已过期）。矛盾点：**ReAct 主循环的调用确实用了 Kimi**（temperature 降级
日志 `model=openai/k3-256k` 实锤），失败的却是管线节点。

## 根因

`AnalysisState`（`src/finance_agent/state.py`）**未声明 `llm_config` 键**。
LangGraph StateGraph 静默过滤 schema 未声明的输入键——两个管线入口
（`api.run_deep_analysis_stream` 与 `agent_factory._make_run_deep_analysis`
闭包）往 `initial_state` 注入的 `llm_config` 根本没进图，全部管线节点
`state.get("llm_config")` 恒为 None → 回退 env（`LLM_MODEL=openai/glm-5.3`
→ 方舟 plan 端点）→ 订阅过期 400。

调用链证据（后端日志时间线，2026-10-04 01:11）：

```
01:11:05 POST /api/analyze
01:11:08 端点拒绝 temperature，降级重试: model=openai/k3-256k   ← ReAct 主循环（带请求配置）✓
01:11:22 k3-256k 降级重试 ✓（工具轮次）
01:11:45 白名单剔除 temperature: model=openai/glm-5.3 × 4      ← 4 分析师并行（管线节点，env 回退）✗
01:11:46 InvalidSubscription → 会话 failed
```

## 为什么 027 门禁没拦住

incident 027 后建立的图通道契约门禁
（`tests/test_graph_5layer.py::TestNodeOutputChannels`）只锁
**节点产出键 ⊆ 声明**，未覆盖**入口 initial_state 键 ⊆ 声明**——
`llm_config` 是入口注入（非节点产出），正好落在门禁盲区。
现有 `tests/test_pipeline_llm_config.py` 全部直接调节点函数（自建 state
dict），同样测不到图边界的 schema 过滤。

## 修复

1. `AnalysisState` 声明 `llm_config: LLMConfig | None`（`state.py`）
2. 门禁补盲区：`TestEntryChannels::test_entry_initial_state_keys_declared`——
   两个入口的 initial_state 全键必须已建图通道，新键未声明即红
3. incident 035 落档（本文档）+ README 索引

## 教训

- 027 的教训只落地成「产出键」门禁，**入口键**同族风险没有同步锁死；
  新增 state 注入键时，通道声明 + 双向门禁（入口/产出）都要过
- 「探针/单节点测试全绿」≠「图边界行为正确」：schema 过滤只发生在
  LangGraph 编译层，任何绕过 graph.stream 的测试都测不到
