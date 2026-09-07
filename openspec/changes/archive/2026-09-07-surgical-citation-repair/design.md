# Design: surgical-citation-repair

## Context

现行 value_mismatch 定向重试 = 目标分析师全量重跑（几十次调用、分钟级、可能引入新错）。FinGround（arXiv 2604.23588）实证：单点有据改写净改善 +71.3%，但修复自身错误引入率 4.1%（单处）→ 14.3%（≥3 处复利），且 52% 误报来自模糊措辞（与我们约数/方向词坑同源）。我们比 FinGround 多两道防线：校验器是确定性纯函数（修复后可强制重校验）、证据是结构化 state（field_ref 直接寻址，不靠检索）。

## Goals / Non-Goals

**Goals**
- 稀疏 value_mismatch（<3 处）走单点改写：1 次 LLM 调用、秒级
- 复利防护：≥3 处回退全量定向重试（阈值取 FinGround 实证拐点）
- 修复后强制重校验，不吞错、不豁免分支、同处不二次修复
- 修复留痕且原桶计数保留（不抹 prompt 归因信号）

**Non-Goals**
- 不做 flag-only 渲染模式（高危场景"只删不修"属渲染侧改造，另行 delta）
- 不扩到 semantic_* 桶（术语/期次错配走受控词表绑定方向，且单点改写对其收益未实证）
- 不改路由函数签名与停滞/上限语义（分流全部收敛在 citation 节点内部）
- 不引入行内引用渲染（FinGround 的单元格级引用是报告渲染层特性，另行评估）

## Decisions

1. **分流在 citation_node 内而非路由层**：`verify_citations` 已持有 per-agent FAIL 明细，在此判定 <3/≥3 并决定是否进入修复子流程；routing.after_citation 语义不动（降低对既有重试门禁测试的波及面）。
2. **修复调用走现有 llm_config 端点，temperature 收紧**：叙事改写需要上下文理解，不宜换更小模型（FinGround 用同族大模型做 revise）；system prompt 固化为模板（出错句 + 前后各一段 + ground_truth + 申报格式示例 + "只改必要处"指令），作为常量入 `citation_repair.py` 并受 prompt 契约测试锁定。
3. **回填策略 = 整句替换**：改写对象是出错句整句（fuzzy 对齐按 FinGround 用 token 编辑距离，实现取最简：句子级定位后整体替换），不做字符级 patch——避免半改写残留。
4. **重校验 = 整体重跑 verify_citations**：不增量只验改动句——coverage 普查是全文函数，且回填可能影响相邻数字认领；全量重跑成本为零（纯函数），没有理由省。
5. **iteration_count 共享**：单点修复轮与全量重试轮共用计数与上限 3，防止"修复 3 轮 + 重试 3 轮"叠加出 6 轮失控。

## Risks / Trade-offs

- 修复改写可能误改相邻句子 → 句子级整体替换 + 全量重校验兜底（新错照常暴露）
- 单点修复让 FAIL 率下降，可能掩盖"分析师申报纪律差"的系统性信号 → value_mismatch_repaired 遥测保留原桶，分桶报告口径连续
- 与 ehr-style-claim-direction 的修复遥测存在口径重叠 → 排序依赖：本 delta 的 repaired 留痕格式与其对齐（proposal Impact 已标注）
