# Proposal: improve-analyst-throughput

## Why

线上事故（2026-08-25，601700 深研管线，docs/incidents 待补 019）：一次深度
分析真实执行 71 分钟才产出报告。两个放大器（在假卡死修复之外）：

1. `technical_analyst` 把 250 期全窗口技术指标序列（MA/MACD/RSI/BOLL/KDJ
   等长 list，含前 N 期 null 预热段）原样 JSON 化进 prompt，单次 LLM 调用
   11.5~14 分钟（其余分析师 20s~3min）。
2. citation 校验三轮全 FAIL（失败率 35%→38%→31%，重试完全无收益），每轮
   仍全量重跑 4 分析师并等最慢的 technical，白白烧掉 ~40 分钟。失败是系统性
   的（claim field_ref 与数据形态不匹配），不是随机噪声，重试修不好。

## What Changes

- 技术指标 context 裁剪：构建 technical_analyst context 时各指标序列只保留
  最近 60 期（不足 60 期保持完整）。
- citation 重试降级：重试轮失败率相对上一轮无显著改善（≥ 上一轮的 80%）时
  提前放行渲染，不再派发下一轮；总轮数上限仍为 3。

## Capabilities

- **New Capabilities**:
  - `analyst-context-budget`（分析师 LLM context 体量预算）
  - `citation-retry-policy`（引用校验重试的降级控制）
- **Modified Capabilities**: 无（两行为在主规范库均无既有条目）

## Impact

- `src/finance_agent/nodes/analysts.py`（technical context 裁剪）
- `src/finance_agent/nodes/citation_node.py` + `src/finance_agent/routing.py`
  （失败率记录与降级路由）
- 纯后端数据管道/路由变更，不涉及前端 UI / SSE 协议，不适用 E2E 门禁。
