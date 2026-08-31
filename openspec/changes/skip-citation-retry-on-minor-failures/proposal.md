# Proposal: skip-citation-retry-on-minor-failures

## Why

契约修复冒烟验证（2026-08-30，incident 022 验证数据）复现了 incident 020 遗留 #1：**任一 FAIL（哪怕 1/46 条，失败率 2.2%）都会使 `citation_pass=False`，触发分析师全量重跑**。实测汉森制药 2 轮、贵州茅台 3 轮、中际旭创 2 轮——重跑轮对单点失败零收益（校验器确定性，同 claim 会再次 FAIL），却每轮白烧 4 分析师全量 LLM 调用（单轮约 12–16 分钟，incident 019/020 成本记录）。既有停滞降级只在「有前一轮数据且失败率不改善」时触发，首轮轻微失败无保护。

## What Changes

- 单轮引用校验失败轻微时 SHALL 直接放行渲染（render），不启动分析师重试轮：**FAIL 数 ≤ 1 且失败率 ≤ 5%**；
- 既有停滞降级与轮数上限（iteration_count < 3）保持不变；
- 触发放行 SHALL 在 trace 观测中留下可判读标记（复用既有降级标记通道）。

## Capabilities

- **Modified Capabilities**: `citation-retry-policy`（扩展「引用校验重试降级」需求：新增轻微失败免重试阈值）

## Impact

- `src/finance_agent/citation_node.py`（失败率计算已存在）与 `src/finance_agent/routing.py`（`after_citation` 增加轻微失败放行分支）；
- 重试经济性：本轮冒烟三标的可省 4 轮 × 4 分析师重跑调用；
- E2E：无交互层变更，不适用前端门禁；
- 不受影响的语义：FAIL>1 或失败率>5% 仍走既有重试/停滞降级路径；真幻觉治理（incident 020 遗留 #2）不属本 delta。