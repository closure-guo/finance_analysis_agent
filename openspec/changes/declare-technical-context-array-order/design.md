# Design: declare-technical-context-array-order

## Approach

一处 context 注记 + 一处 prompt 反幻觉规则（零业务逻辑改动）：

1. `analysts.py::_build_technical_context` 在序列注记末尾追加「序列为时间正序（旧→新），列表末尾为最新一期；引用 -1 时核对末尾元素」——与既有的「各序列为最近 60 期，更早历史已省略」合并成一句，token 成本可忽略。
2. `prompts/technical_analyst.md` 反幻觉硬规则内增加自证约束：「引用负索引值前先定位序列尾部（-1=最后一个元素），不得把展示首元素或记忆中的历史行情当作最新值」。

校验器 `citation.py` 与 argue、容差语义保持冻结（Incident 022 归因：负索引解析正确，858.32=真实最新 MA5；problem 在 LLM 对容器方向的默认假设）。

## Alternatives Considered

- **方案 A：仅改 prompt 文字**（selected）：最小侵入，直击歧义源；context 和 prompt 双点锚定，防止单一改漏。
- **方案 B：校验器加「方向检测」**：不选——把 LLM 展示歧义的赔偿责任转嫁给确定层属误诊；且 state 序列方向已由 `fetch_kline` 锁定（正序），无歧义可检。
- **方案 C：resolver 反转容忍**：不选——会引入第二份方向真相源，且修复前已证解析正确，改 resolver 是修错对象。

## Risks

- 低：context 文本与 prompt 改动若未同步发布（`deploy_prompts.py`），eval 门禁拒绝运行（spec prompt-deploy-consistency）；
- 归因残留：即使方向声明生效，LLM 仍可能读错数值（真幻觉），由 citation 校验器负责拦截——本 delta 只消除「容器方向歧义」这一定向错位源；
- 回归网：incident 022 附录 13 条样本（stated=窗口首元素）钉死为修复后 FAIL→PASS 的对照集，纳入 TDD 复现测试。