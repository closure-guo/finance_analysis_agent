# Delta for data-source-resilience

## MODIFIED Requirements

### Requirement: 行情 quote 二级回退（百度估值 + 腾讯日线）

系统在获取个股行情（`fetch_stock_quote`）时 SHALL 按优先级回退：东方财富 `stock_zh_a_spot_em`（主源，含 PE/PB/市值/价格全字段）→ 百度估值 `stock_zh_valuation_baidu` 总市值/市净率 + 腾讯 `stock_zh_a_hist_tx` 最新收盘价（估值/价格字段）→ 仅名称 fallback（保底）。任一有值字段 SHALL 并入 result，不覆盖主源已有字段。

- 百度估值取 `总市值`（→ `market_cap`）与 `市净率`（→ `PB`），各独立 try/except（任一失败不影响其余）；取值最后一行（最新日）。
- 腾讯日线用 `_to_sina_symbol` 前缀（`688072`→`sh688072`）、recent 最新收盘 → `price`。
- PE/市值推导 SHALL NOT 在 quote 内进行（PE 语义依赖财务口径）；PE 缺失时下游 compute SHALL 按 valuation-signal-integrity 规范的 TTM 规则确定性推导 `PE_ttm` 并以推导值参与估值维度（GARP/相对估值/上下文注入），SHALL NOT 静默跳过估值维度。
- 主源（东财）可用时 SHALL NOT 触发任何回退，行为与无回退版本一致。
- 全部回退后仅剩名称时保留 ERROR 日志（维度缺失可观测）。

(Previously: PE/市值推导 SHALL NOT 在 quote 内进行（PE 语义依赖财务口径，留给下游 compute/charts 处理）；PE 缺失时下游 `or` 守卫照常跳过估值维度。)

#### Scenario: 东财失败回退百度+腾讯

- **WHEN** `fetch_stock_quote("688072")` 且东财 `stock_zh_a_spot_em` 抛异常/返回空
- **THEN** 系统 SHALL 调用百度 `stock_zh_valuation_baidu` 取 `market_cap` 与 `PB`
- **AND** SHALL 调用腾讯 `stock_zh_a_hist_tx("sh688072")` 取最新收盘为 `price`
- **AND** 返回 dict 含 `market_cap`/`PB`/`price`（值有则并）

#### Scenario: 百度某指标失败不影响其余

- **WHEN** 百度 `总市值` 成功而 `市净率` 抛异常
- **THEN** 结果 SHALL 含 `market_cap`，SHALL NOT 抛异常，`PB` 保持缺失

#### Scenario: 回退后 PE 缺失不静默跳过估值

- **WHEN** quote 经百度回退返回（含 `market_cap`/`PB`/`price`、无 `PE`）
- **AND** 下游 compute 拥有年报与最新累计报告期归母净利润
- **THEN** compute SHALL 推导 `PE_ttm` 并注入估值维度
- **AND** 相对估值与 GARP SHALL 以 `PE_ttm` 参与，SHALL NOT 因 `PE` 缺失整体跳过
