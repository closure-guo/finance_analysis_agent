# Design: report-render-operational-params

## Context

`report.py::_format_trade_decision` 是报告「交易决策」节的唯一渲染入口，输入为 `TradeDecision` 对象或 dict（report.py:184/361 处 `final_trade_decision or trader_plan` 回退取值）。当前只取 action/confidence/reasoning 与价位修正标记。该函数被 Markdown 报告与 Word/PPT/PDF 导出共用，改一处全链路生效。

决策 JSON 的字段形态（models.py `TradeDecision`）：`position_size` 恒为 light/moderate/heavy 之一；`entry_price`/`stop_loss`/`target_price` 为 float，**0 值语义有二义**——trader.md 要求 watch 类可不填，但 watch 被校验通过时字段可能是 0 而非 null（比亚迪 sell 案例即 stop/target/entry 全 0）。渲染层必须区分「有效价位」与「未提供」。

## Goals / Non-Goals

**Goals:**

- 报告决策节与系统实际执行的决策参数一致（所见即所执行）
- 0/null/缺失统一如实标注「未提供」，不复现「占位数据冒充参数」的旧病
- watch/hold 不渲染硬价格，保留触发条件指引（当前触发条件只在 reasoning 自由文本中）
- 保留 toolize-price-levels 价位修正标注

**Non-Goals:**

- 不给 TradeDecision 新增结构化触发条件字段（属 trader prompt/契约变更，另立 delta；本改动只在 watch/hold 分支注明「触发条件见理由」）
- 不改导出管线（Markdown 变更自动被 Word/PPT/PDF 导出继承）
- 不动 judge 材料（evals/extract.py 的决策序列化已有独立预算与格式，口径不受影响）

## Decisions

1. **渲染入口只改 `_format_trade_decision` 一处**：函数内按 action 分支（buy/sell 渲染价格行；watch/hold 渲染触发条件指引行）。不引入新模板层——该函数已是唯一事实源，且历史缺陷（FM 盲审批、dict 守卫跳过对象）均证明「渲染层自建守卫」风险高，直接 `isinstance(TradeDecision)` + `model_dump()` 双形态兼容沿用现有写法。

2. **「有效价位」判定：`value and value > 0`**：0 与负值均视为「未提供」（正常价位不可能为 0 或负；止损为负的做空语义本系统不支持）。判定函数独立小工具 `_fmt_price(value)`，返回格式化字符串或「未提供」，避免三处重复三处漂移。

3. **依赖顺序：规范先行、实现押后**：本 delta 的 spec 归档不依赖 harden-decision-report-semantics；但 `_format_trade_decision` 与 harden 变更触及的 report.py 区域相邻，实现任务排在 harden 归档之后执行，避免同文件合并冲突。tasks.md 中以独立任务组标注该前置。

## Risks / Trade-offs

- **0 值二义性**：若未来出现「0 是合法价位」的场景（如指数点位），`value > 0` 判定会误标「未提供」——届时在 `_fmt_price` 单点修判定即可，测试先行。
- **报告变长**：buy/sell 决策节新增 3 行，报告模板纵向空间受轻微影响；验收时人工检查报告版式。
- **watch 触发条件仅为指引**：用户可能期望结构化触发条件清单；明确为 Non-Goal 并在 spec 中写死「不得凭空结构化」，防止实现时越界编造。
