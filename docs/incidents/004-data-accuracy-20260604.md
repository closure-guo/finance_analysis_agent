# 004: 数据准确性系统性问题 — efficiency 年份错位 + ROE 口径 + LLM 自算

**日期**: 2026-06-04
**状态**: 已修复（#12 #13 #14）
**触发**: 300308 中际旭创端到端审查

---

## 问题描述

300308 投资分析报告交叉比对 iFinD 数据，发现 6 处偏差。经验证，根因非 LLM 幻觉，而是**系统层面的计算 bug 和口径差异**。

| # | 指标 | 报告值 | iFinD 值 | 根因 |
|---|------|--------|----------|------|
| 1 | ROE | 36.27% | 44.16% | 公式口径：期末权益 vs 加权平均 |
| 2 | 存货周转率同比 | +10.7% | -19.3% | efficiency.py 年份错位 bug |
| 3 | 利息保障增长 | +91.4% | +194.6% | 公式口径：EBIT vs 现金流 |
| 4 | 净利率同比 | +30.3% | +34.5% | 口径差异（影响小） |
| 5 | FCF 增长率 | 2624.6% / 2626.4% | 2626.4% | LLM 自算不一致 |
| 6 | 现金流覆盖比率 | 2720.2% | 无法验证 | LLM 编造 |

---

## 根因分析

### P0: efficiency.py 年份错位（确认是 bug）

`src/finance_agent/metrics/efficiency.py:48` 使用 `indicators.iloc[i]` 按行号索引。

- `indicators` 按日期**升序**（2020→2024）
- `balance_sheet` / `income_statement` 按日期**降序**（2025→2021）
- 结果：`i=0`（BS 的 2025 年）取到 `indicators.iloc[0]`（2020 年数据）

验证：AKShare indicators 2024 年存货周转率 = 2.7843，与 iFinD 的 2.78 完全一致。**数据源没问题，纯粹是代码错位。**

影响：**每只股票都受影响**，不只是 300308。

### P1: ROE 口径

`src/finance_agent/metrics/profitability.py:79` 使用 `归母净利润 / 期末归母权益`。

行业标准是**加权平均 ROE**（证监会口径）。300308 权益从 191 亿增至 298 亿（+56%），期末权益做分母严重低估 ROE。

AKShare indicators 提供 `加权净资产收益率(%)` 字段，但只到 2024 年。

### P2: LLM 自算/编造未提供指标

系统不计算 FCF 增长率、现金流覆盖比率同比等指标。LLM 从原始数据自行推算：
- FCF 增长率在报告第 5 章和第 6 章算出不同结果（2624.6% vs 2626.4%）
- 现金流覆盖比率 2720.2% 无任何可验证的计算路径

---

## 修复过程

### 调查阶段：根因判断经历了两次修正

**初判**：LLM 幻觉（6 个问题全部归因于 LLM 编造）

**第一次修正**：调用 AKShare 接口重跑 300308 数据后发现：
- ROE 36.27% 是系统正确计算的（归母净利润/期末归母权益），不是 LLM 编造
- 存货周转率 +10.7% 也是系统算出来的（基于错位数据）
- 利息保障 +91.4% 同理

根因从"LLM 幻觉"修正为"数据源差异 + LLM 幻觉混合"。

**第二次修正**：读取 AKShare indicators 全部字段后发现：
- indicators 2024 年存货周转率 = 2.7843，与 iFinD 的 2.78 完全一致
- 系统返回的 2025 年存货周转率 1.6747 实际是 indicators 2020 年的值

根因从"数据源差异"修正为"**代码 bug（年份错位）**"。AKShare 数据源本身可靠。

**最终定案**：6 个问题中 0 个是 LLM 编造系统已提供的指标。LLM 只在系统不提供的指标上自算/编造（FCF 增长率、现金流覆盖比率）。

### #12: efficiency 年份错位修复（TDD）

**3 个 RED→GREEN 循环：**

1. **日期匹配**：构造 indicators 升序 + BS 降序 + 年份不完全重叠的 fixture，断言 2024 应取 7.0 而非行号错位的 6.0。修复：`indicators.iloc[i]` → `_find_indicator(indicators, year)` 按年份匹配。

2. **缺失年份自算**：indicators 无 2025 年数据时，断言应自算 `营业成本/平均存货` 而非返回 None。修复：fallback 分支加入 `cost / ((inventory + prev_inventory) / 2)`。

3. **来源标注**：断言返回值包含 `存货周转率_source` 区分 official/calc。修复：在取 indicators 和自算分支分别标注。

**遇到的问题**：加了 `存货周转率_source` 字符串值后，compute.py 的 `_calc_growth_rates` 尝试对字符串做减法（"official" - "official"）导致 TypeError。修复：在 compute.py 组装 all_metrics 时过滤 `_source` 后缀的 key。

### #13: ROE 口径修复（TDD）

**2 个 RED→GREEN 循环：**

1. **加权 ROE 优先**：构造 indicators 含 `加权净资产收益率(%)` 的 fixture，断言 ROE 应取加权值 44.16 而非期末权益自算值 28.97。修复：profitability.py 先查 indicators，有加权值直接用。

2. **缺失年份平均权益**：indicators 无 2025 年数据时，断言用 `(期初权益+期末权益)/2` 作分母。修复：fallback 分支改为 `(equity + prev_equity) / 2`。

**遇到的问题**：修改后 conftest indicators 没有 `加权净资产收益率(%)` 字段，走了平均权益 fallback，导致旧测试断言失败（28.33% → 29.57%）。修复：在 conftest indicators 中加入该字段，值设为旧测试预期值，保持兼容。

**复用**：profitability.py 复用了 efficiency.py 的 `_find_indicator` 函数，通过 import 共享。

### #14: LLM 防幻觉

**发现**：计划是"补算 FCF 增长率"，但实际验证发现 FCF 增长率已经在 growth_rates 中（cashflow.py 计算 FCF，compute.py 的 `_calc_growth_rates` 自动生成增长率）。问题不是缺数据，是 LLM 忽略了系统提供的数据自行计算。

**修复**：
- 新增回归测试确认 FCF 增长率在 growth_rates 中
- ia_analyze.md 增加第 9 条约束：禁止自行计算系统未提供的指标，缺失必须标注"数据不可用"

---

## 经验教训

1. **指标数据对齐必须按日期匹配，不能按行号**。不同 DataFrame 的排序方向和行数可能不同。
2. **"数据源差异"的判断需要验证**。本次最初归因为 AKShare vs iFinD 差异，实际 AKShare 2024 数据与 iFinD 完全一致，问题在代码。
3. **LLM 忠实报告了系统给它的数据**。6 个偏差中只有 2 个是 LLM 幻觉，其余 4 个是系统计算正确但口径/对齐有误。
4. **TDD 对 bug 修复的价值**：tracer bullet 测试用生产环境场景（indicators 升序 + BS 多一年）暴露 bug，比现有 fixture（恰好对齐）更有效。
5. **修改返回结构要检查下游消费者**：加 `_source` 字段导致 compute.py 尝试计算字符串的增长率，需要在组装 all_metrics 时过滤非数值字段。
6. **先验证再归因**：计划说"补算 FCF 增长率"，但实际验证发现已经算好了。省掉了不必要的代码改动。
