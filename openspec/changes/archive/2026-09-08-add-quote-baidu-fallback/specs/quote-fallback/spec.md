# Delta Spec: quote-fallback

## ADDED Requirements

### Requirement: 行情 quote 二级回退（百度估值 + 腾讯日线）

系统在获取个股行情（`fetch_stock_quote`）时 SHALL 按优先级回退：东方财富 `stock_zh_a_spot_em`（主源，含 PE/PB/市值/价格全字段）→ 百度估值 `stock_zh_valuation_baidu` 总市值/市净率 + 腾讯 `stock_zh_a_hist_tx` 最新收盘价（估值/价格字段）→ 仅名称 fallback（保底）。任一有值字段 SHALL 并入 result，不覆盖主源已有字段。

- 百度估值取 `总市值`（→ `market_cap`）与 `市净率`（→ `PB`），各独立 try/except（任一失败不影响其余）；取值最后一行（最新日）。
- 腾讯日线用 `_to_sina_symbol` 前缀（`688072`→`sh688072`）、recent 最新收盘 → `price`。
- PE/市值推导 SHALL NOT 在 quote 内进行（PE 语义依赖财务口径，留给下游 compute/charts 处理）；PE 缺失时下游 `or` 守卫照常跳过估值维度。
- 主源（东财）可用时 SHALL NOT 触发任何回退，行为与无回退版本一致。
- 全部回退后仅剩名称时保留 ERROR 日志（维度缺失可观测，与 fix(data) 日志契约一致）。

#### Scenario: 东财失败回退百度+腾讯

- **WHEN** `fetch_stock_quote("688072")` 且东财 `stock_zh_a_spot_em` 抛异常/返回空
- **THEN** 系统 SHALL 调用百度 `stock_zh_valuation_baidu` 取 `market_cap` 与 `PB`
- **AND** SHALL 调用腾讯 `stock_zh_a_hist_tx("sh688072")` 取最新收盘为 `price`
- **AND** 返回 dict 含 `market_cap`/`PB`/`price`（值有则并）

#### Scenario: 百度某指标失败不影响其余

- **WHEN** 百度 `总市值` 成功而 `市净率` 抛异常
- **THEN** 结果 SHALL 含 `market_cap`，SHALL NOT 抛异常，`PB` 保持缺失

#### Scenario: 全部回退失败仅名称

- **WHEN** 百度与腾讯均失败（网络异常）
- **THEN** 系统 SHALL 返回仅名称 fallback，SHALL 留 ERROR 日志（行情各维度缺失）

#### Scenario: 东财正常不触发回退

- **WHEN** 东财 `stock_zh_a_spot_em` 返回非空且匹配到股票
- **THEN** 系统 SHALL 直接返回全字段 quote，SHALL NOT 调用百度/腾讯