# valuation-signal-integrity Specification

## Purpose
由 delta update-financial-freshness-and-valuation 归档建立（2026-09-29 实施完毕并通过独立终审）。
## Requirements
### Requirement: PE 缺失时的 TTM 确定性推导

compute 层 SHALL 在 `quote.PE` 缺失且 `market_cap` 可得时，按 TTM 口径确定性推导 `PE_ttm = market_cap / TTM 归母净利润`。TTM 归母净利润 SHALL 由「最新年报归母净利润 − 最新年报内与最新累计报告期同期的归母净利润 + 最新累计报告期归母净利润」拼合；当最新报告期即年报时 TTM 直接取年报值。推导 MUST 为纯规则计算（不经过 LLM）；`market_cap` 或 TTM 任一缺失/非正时 `PE_ttm` SHALL 为 None 并注明缺失原因，MUST NOT 产出 0、无穷或 NaN。推导值 SHALL 标注口径为 `derived_ttm`，与主源静态 PE 可区分。

#### Scenario: 中报已披露时拼合 TTM

- GIVEN `market_cap` = 1910.23 亿、FY2025 归母净利润 9.27 亿、2026H1 归母净利润 13.43 亿、2025H1 归母净利润 0.94 亿
- WHEN compute 执行 PE 推导且 quote.PE 缺失
- THEN TTM 归母净利润 SHALL ≈ 21.76 亿（9.27 − 0.94 + 13.43）
- AND `PE_ttm` SHALL ≈ 87.8，口径标注 `derived_ttm`

#### Scenario: 推导输入缺失时留空

- GIVEN `market_cap` 缺失（行情全回退失败）
- WHEN compute 执行 PE 推导
- THEN `PE_ttm` SHALL 为 None 且 details 注明「market_cap 缺失」
- AND MUST NOT 以 0、无穷或邻股数据填充

#### Scenario: 主源 PE 存在时不覆盖

- GIVEN quote 携带主源静态 `PE`
- WHEN compute 装配估值维度
- THEN SHALL 保留主源 `PE`，`PE_ttm` 可并存但标注口径
- AND 估值比较 SHALL 优先使用与同业口径一致的那个并注明

### Requirement: 估值缺数据的诚实文案

估值组件（GARP、相对估值）在估值输入缺失时 SHALL 输出「数据缺失（未参与比较）」类诚实文案与 `missing` 标注，MUST NOT 将缺失渲染成比较失败（如 `PE >= 行业平均`）。比较失败与数据缺失 SHALL 在 failures/details 中分桶可辨。

#### Scenario: GARP 无 PE 时报缺失而非伪失败

- GIVEN `quote.PE` 与 `PE_ttm` 均为 None（推导输入缺失）
- WHEN GARP 筛选执行
- THEN failures SHALL 含「PE 数据缺失（未参与比较）」
- AND MUST NOT 输出「PE >= 行业平均」
- AND details 中 PE 相关项 SHALL 标注 missing 而非数值

#### Scenario: 有 PE_ttm 时 GARP 正常比较

- GIVEN `PE_ttm` = 87.8、行业平均 PE = 45
- WHEN GARP 筛选执行
- THEN failures SHALL 含「PE >= 行业平均」（真实比较失败）
- AND details SHALL 记录 PE = 87.8 与口径 `derived_ttm`

### Requirement: 估值数据注入分析师上下文

基本面分析师上下文 SHALL 包含估值数据段：PE（含口径：主源静态/derived_ttm）、PB、market_cap、相对估值结论（可计算时）。当估值维度整体缺失时，上下文 SHALL 显式标注「估值数据缺失」，MUST NOT 省略该段使分析师默认估值不可知。

#### Scenario: 回退运行下估值段进入上下文

- GIVEN 东财封锁、百度回退提供 `market_cap`=1910.23 亿与 `PB`=15.02，`PE_ttm` 推导为 87.8
- WHEN 基本面分析师构建上下文
- THEN 上下文 SHALL 含 market_cap、PB、PE_ttm（口径 derived_ttm）与相对估值结论
- AND 分析师报告的估值论断 SHALL 可引用这些数值

#### Scenario: 估值维度整体缺失时显式声明

- GIVEN 行情全回退失败、PE 推导输入缺失
- WHEN 基本面分析师构建上下文
- THEN 上下文 SHALL 含「估值数据缺失」标注段
- AND 基本面报告 SHALL 声明估值维度缺失对结论的影响，MUST NOT 在无数值情况下断言贵贱
