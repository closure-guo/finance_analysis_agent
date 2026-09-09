# Delta Spec: data-source-resilience

## ADDED Requirements

### Requirement: 个股日 K 线三级回退（东财/新浪/腾讯）

系统在拉取个股日 K 线（`fetch_kline`）时 SHALL 按三级优先级回退：东方财富 `stock_zh_a_hist`（主源）→ 新浪 `stock_zh_a_daily` → 腾讯 `stock_zh_a_hist_tx`；任一源成功 SHALL 立即返回（升序 + tail(days)，列名归一同构中文列），全部失败 SHALL 返回空 DataFrame 不抛异常。

- 腾讯回退使用 `_to_sina_symbol` 前缀（`600519`→`sh600519`）、`adjust="qfq"`，返回列按 `date→日期/open→开盘/close→收盘/high→最高/low→最低/volume→成交量/amount→成交额/turnover→换手率` 归一化。
- 主源（东财）可用时 SHALL NOT 触发任何回退，行为与无回退版本一致。

#### Scenario: 东财与新浪均失败回退腾讯

- **WHEN** `fetch_kline("600519")` 且东财 `stock_zh_a_hist`、新浪 `stock_zh_a_daily` 均抛异常/返回空
- **THEN** 系统 SHALL 调用腾讯 `stock_zh_a_hist_tx("sh600519", adjust="qfq")`
- **AND** 返回列 SHALL 含 `日期`/`收盘`（归一化），升序 + tail(days)

#### Scenario: 腾讯也失败返回空

- **WHEN** 三级均失败
- **THEN** 系统 SHALL 返回空 DataFrame，SHALL NOT 抛异常

#### Scenario: 东财正常不触发回退

- **WHEN** 东财 `stock_zh_a_hist` 返回非空
- **THEN** 系统 SHALL 直接返回，SHALL NOT 调用新浪/腾讯