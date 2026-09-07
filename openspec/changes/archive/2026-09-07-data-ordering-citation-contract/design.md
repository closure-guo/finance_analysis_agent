# Design: data-ordering-citation-contract

## Context

真实运行（中际旭创）暴露双重问题：① akshare 宏观/财务接口返回**降序**（最新在前），代码用 `tail()`/`[-3:]`（假设升序）→ 取到 2008 旧数据；② citation `field_ref` 索引语义未定义 → 分析师 context 子集（`[-3:]`）的「index 0」与校验方解析的完整列表「index 0」指向不同元素 → citation 误报 FAIL → 重试环空转。

已有约定线索：财务三表已是「降序、最新在前」——`_filter_annual` 保留年报后仍降序，`_trim_years` 用 `df.head(years)` 取最新 N 年（akshare_client.py）；quarterly profit 注释「按报告日排序（最新的在前）」。**本 delta 把「降序、index 0 = 最新」确立为全仓时间序列数据的统一契约。**

## Goals / Non-Goals

**Goals:**
- 明确取数顺序契约：时间序列「降序、index 0 = 最新一期」；fetch 层显式排序。
- 明确 citation field_ref 解析契约：list index 相对 state 完整列表、index 0 = 最新；分析师 context 从 index 0 开始展示。
- 按契约修复宏观/财务取数与 context，消除 2008 旧数据与 citation 误报。
- 复现测试先行。

**Non-Goals:**
- 不改变 LLM prompt 结构、SSE 事件、API schema、citation 校验算法（容差/规则不变）。
- 不重排 chart 展示顺序（图表消费端仍按自身 x 轴升序展示——由图表层自行处理，不在本 delta 范围）。

## Decisions

### D1: 时间序列统一「降序、index 0 = 最新一期」

所有进入 state 的时间序列数据（宏观指标、财务三表、财务指标、K 线）统一约定 **index 0 = 最新一期**，fetch 层**显式排序**保证（不依赖数据源的隐藏顺序）。
- **理由**：对齐财务三表既有约定（`_trim_years` 已按此用 `head(years)`）；显式排序使契约对 akshare 顺序变化稳定。
- **实施**：`fetch_macro_indicators` 对每个宏观 df `sort_values(首列, ascending=False)` 后 `head(6)`；财务三表 fetch 若未显式排序则补排序（实现期核实 `_sina_report` 是否保证降序）；K 线保持现状（升序数据由图表层消费，本 delta 不强改）。

### D2: citation field_ref 的 list index 相对 state 完整列表

`field_ref`（如 `macro_indicators.cpi.0.全国-同比增长`）中的 list index **相对 state 中完整列表**解析：`cpi[0]` = 最新一期（D1 约定）。校验方 `_resolve_field_ref` 按此解析 ground truth。
- **理由**：field_ref 是绝对引用（state 路径），必须与分析师看到的数据一致才有意义；D1 的「index 0 = 最新」让索引语义稳定、可预期。

### D3: 分析师 context 必须从 index 0 开始展示

任何给分析师展示的时间序列**子集**必须**从 index 0 开始**（取 `[:N]` 而非 `[-N:]`），保证分析师引用的 `field_ref` 索引与校验方解析的索引对齐。
- **理由**：`[-N:]` 的子集起点 ≠ 0，导致分析师「index 0」与完整列表「index 0」错位（本次 citation FAIL 的直接原因）。
- **实施**：`_build_macro_context` `records[-3:]` → `records[:3]`；`_build_fundamental_context` `df.tail(3)`/`indicators.tail(3)` → `head(3)`（数据降序后 head = 最新且从 index 0 开始）。

### D4: 修复不改变校验算法

citation 校验的数值比较（绝对容差 0.01 / 相对 0.5%）、状态语义（PASS/FAIL/UNVERIFIABLE）不变，仅修正数据排序与索引对齐。

## Risks / Trade-offs

- [akshare 某宏观接口首列非日期列] → D1 实现期核对各接口列名，按实际日期列排序（记入测试断言）。
- [财务三表 fetch 层未显式排序，依赖 akshare 现状] → 实现期核实 `_sina_report` 顺序并补显式排序；若改动面大则仅在 analysts.py context 层按降序假定修复（记录为待办）。
- [K 线保持升序与「降序」约定不一致] → K 线由图表层按自身逻辑消费，不在本契约覆盖（documented 例外）。

## Migration Plan

1. delta 落地 → 2. 复现测试（mock 降序数据）→ 3. 修复 fetch + context → 4. 全量回归 + 实跑对账（Langfuse 确认宏观/财务引用最新数据、citation 不再误报）→ 5. sync + archive。

## Open Questions

- `financial_indicators`（compute_metrics 产出）的排序是否与财报一致（降序）——实现期核实，必要时补排序。
- 财务三表 fetch 是否需显式排序（`_sina_report` 顺序依赖）——实现期核实后定。
