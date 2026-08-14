# Proposal: data-ordering-citation-contract

## Why

排查一次真实分析（中际旭创）时发现系统性数据问题：akshare 宏观接口（`macro_china_cpi`/`pmi`/`money_supply`）返回**降序**数据（最新在前），而代码多处用 `tail()`/`[-3:]` 取「最近」却假设升序 → 宏观/基本面分析师拿到的是 **2008 年的旧数据**（宏观 6 期全为 2008、财报「近3年」取到 2008-2010）。进一步地，citation 校验的 `field_ref` 索引语义**从未定义**：分析师 context 展示的是完整列表的**子集**（`[-3:]`），它眼中的「`cpi.0`」与校验方解析的「完整列表 `cpi[0]`」指向**不同元素** → 3 个 citation 误报 FAIL → 引用验证重试环跑满 3 轮空转。

这不是单纯的实现 bug，而是**两个契约缺失**：① 取数顺序约定；② citation field_ref 解析契约。本次以 delta 明确契约并按契约修复。

## What Changes

- **明确取数顺序约定**：时间序列数据统一「降序、index 0 = 最新一期」；fetch 层显式排序，不依赖 akshare 的隐藏顺序。
- **明确 citation field_ref 解析契约**：field_ref 的 list index 相对 **state 完整列表**（index 0 = 最新一期）；分析师 context 展示的数据必须**从 index 0 开始**（取 `[:N]` 而非 `[-N:]`），保证分析师引用的索引与校验方解析的索引一致。
- **修复实现**：`fetch_macro_indicators` 显式降序 + `head(6)`；`_build_macro_context` `records[:3]`；`_build_fundamental_context` `df.head(3)`/`indicators.head(3)`。
- 复现测试先行：mock 降序数据断言「最近」取到的是最新一期。

## Capabilities

### New Capabilities

- `data-fetching`: 数据取数契约——时间序列数据的排序约定（降序、index 0 = 最新）、取数窗口、排序稳定性要求。
- `citation-verification`: 引用校验契约——`field_ref` 的解析语义（list index 相对 state 完整列表、index 0 = 最新一期）、分析师 context 与校验方的一致性要求、ground-truth 来源。

### Modified Capabilities

（无）

## Impact

- **代码**:
  - `src/finance_agent/data/akshare_client.py` — `fetch_macro_indicators` 排序 + `head(6)`。
  - `src/finance_agent/nodes/analysts.py` — `_build_macro_context` `[:3]`、`_build_fundamental_context` `head(3)`。
- **测试**: 新增 `tests/test_macro_order_fix.py`（复现降序数据 bug）+ 相关回归。
- **行为**: 分析师使用真·最新数据；citation 校验不再因索引错位误报；重试环不再空转。纯数据排序/展示修复，不改变 LLM prompt 结构、SSE 事件、API schema。
- **契约**: 新增 `openspec/specs/data-fetching/spec.md` 与 `openspec/specs/citation-verification/spec.md`。
