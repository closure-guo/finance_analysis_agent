# Delta for valuation-signal-integrity

## MODIFIED Requirements

### Requirement: 估值缺数据的诚实文案

估值组件（GARP、相对估值）在估值输入缺失时 SHALL 输出「数据缺失（未参与比较）」类诚实文案与 missing 标注，MUST NOT 将缺失渲染成比较失败。诚实分桶 SHALL 覆盖 GARP 全部四个输入（PE、净利润增长率、ROE、负债率）：任一输入为 None 或 NaN 时，对应项 SHALL 输出「<指标> 数据缺失（未参与比较）」并在 details 标注 `<指标>_missing`，MUST NOT 输出「<指标> <= 阈值」类伪比较文案，NaN MUST NOT 因比较恒 False 被伪装成通过。比较失败与数据缺失 SHALL 在 failures/details 中分桶可辨。

(Previously: 估值组件（GARP、相对估值）在估值输入缺失时 SHALL 输出「数据缺失（未参与比较）」类诚实文案与 missing 标注，MUST NOT 将缺失渲染成比较失败（如 PE >= 行业平均）。比较失败与数据缺失 SHALL 在 failures/details 中分桶可辨。——原实现仅覆盖 PE 项。)

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

#### Scenario: ROE 缺失时报缺失而非伪失败

- GIVEN ROE 为 None（年报序列缺失该年值）
- WHEN GARP 筛选执行
- THEN failures SHALL 含「ROE 数据缺失（未参与比较）」
- AND MUST NOT 输出「ROE <= 15%」
- AND details SHALL 标注 `ROE_missing`

#### Scenario: 负债率 NaN 视同缺失不伪装通过

- GIVEN 负债率输入为 NaN（NaN 参与比较恒 False）
- WHEN GARP 筛选执行
- THEN failures SHALL 含「负债率 数据缺失（未参与比较）」
- AND SHALL NOT 因 NaN 比较恒 False 而让负债率项静默通过
- AND details SHALL 标注 `负债率_missing`

#### Scenario: 净利润增长率缺失报缺失

- GIVEN 净利润增长率为 None
- WHEN GARP 筛选执行
- THEN failures SHALL 含「净利润增长率 数据缺失（未参与比较）」
- AND MUST NOT 输出「净利润增长率 <= 15%」
