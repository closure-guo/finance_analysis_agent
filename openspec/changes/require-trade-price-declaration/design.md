# Design: require-trade-price-declaration

## Context

连续 4 轮真实运行 trader 从不申报数值价位（round8 E2E 3/3 + round9 宁德 buy 三价全 null），根因是 `validate.py` 对 buy/sell 价位缺失静默 pass（「schema 可选，跳过校验」），trader 无反馈压力。价位是 buy/sell 的承重参数：报告操作参数、derived_metrics（止损距离/赔率）、price_check 参考带校验全部依赖它。

## Goals / Non-Goals

**Goals**
- buy/sell 价位缺失获得确定性反馈（fail 打回一次），trader 被迫申报数值价位
- 激活 derived_metrics 真实数据路径（派生指标进风险辩论）
- 解锁 report-render buy+真实价位的真实报告核对

**Non-Goals**
- 不改 TradeDecision schema（字段保持可选——打回放行路径需要 schema 宽松，必填约束由 prompt 契约 + validate 打回承担）
- 不改报告渲染（「未提供」兜底已就位）
- 不重构 RJ 裁决价位与 trader_plan 价位的派生链路（现有设计：validate 时基于 trader_plan 计算）

## Decisions

### 1. 缺失判定 = None / ≤0，三价统一
`entry/stop/target` 任一为 None、0 或负数即「缺失」（0 是 LLM 实际输出的「未提供」形态——比亚迪 sell 0/0 已在报告中按未提供渲染）。三价统一处理，不单独豁免 entry。

### 2. 首次缺失 fail 打回，二次缺失放行+如实标注
复用现有 `price_check_attempts<1` 打回回路，feedback 列明缺失项与申报要求。二次仍缺失 → pass + note「已打回仍未申报」，不虚构、不估算（报告「未提供」兜底）。**备选否决**：无限打回——死循环风险；schema 强制必填——打回放行路径需要 schema 宽松。

### 3. 价位缺失不参与「工具修正」路径
现有「二次不合法→按参考带修正」适用于「有数值但不合法」；缺失无数值可修，故走放行+标注，不进 corrected 路径。

### 4. prompt 契约与 validate 双保险
trader.md（buy/sell MUST 申报三价）+ risk_judge.md（继承价位可调数值不得置 null）+ validate 打回兜底。单靠 prompt 不可靠（4 轮实证），单靠打回会浪费一轮生成——双保险。

## Risks / Trade-offs

- [打回增加一次 LLM 调用（首次 buy/sell 无价位时）] → 上限 1 次，且这是修正行为缺陷的必要成本；prompt 契约上线后打回率预期快速下降
- [trader 可能申报离谱价位] → 既有参考带校验（±2ATR）与 entry 偏差上限（15%）不变，照常拦截
- [watch 决策误打回] → direction is None 分支前置，watch/hold 行为不变（测试锁定）

## Migration Plan

代码 + prompt 合入 → deploy_prompts 发布 → 单元测试全绿 → 真实运行验证（buy 决策带价位报告核对，需 Docker/Langfuse 恢复）→ 归档。回滚 = revert validate.py 与 prompt 提交。

## Open Questions

- 无
