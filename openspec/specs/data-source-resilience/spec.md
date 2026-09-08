# data-source-resilience Specification

## Purpose
TBD - created by archiving change data-source-benchmark-fallback. Update Purpose after archive.
## Requirements
### Requirement: 指数 K 线失败回退新浪

系统在拉取指数日 K 线（`fetch_index_kline`）时 SHALL 优先使用东方财富 `index_zh_a_hist`；当主源调用失败（网络错误/重试耗尽）或返回 DataFrame 为空时，SHALL 回退调用新浪 `stock_zh_index_daily`（按指数代码转新浪符号，如 `000300` → `sh000300`）。

- 主源成功时 SHALL NOT 触发回退，行为与无回退版本完全一致（含列名、排序、tail(days) 截断）。
- 主源失败但回退成功时 SHALL 返回回退数据，列名 SHALL 归一化为主源同构中文列。
- 主源与回退均失败时 SHALL 返回空 DataFrame，行为与现状一致（下游按既有缺失逻辑处理）。

#### Scenario: 东财正常直接返回

- **WHEN** `fetch_index_kline("000300")` 且东财 `index_zh_a_hist` 返回非空
- **THEN** 系统 SHALL 直接返回东财数据（升序 + tail(days)），SHALL NOT 调用新浪

#### Scenario: 东财失败回退新浪

- **WHEN** 东财 `index_zh_a_hist` 抛连接异常或返回空 DataFrame
- **THEN** 系统 SHALL 调用新浪 `stock_zh_index_daily("sh000300")`
- **AND** 返回列 SHALL 含 `日期` 与 `收盘`（经 rename 归一化），且与东财输出列名一致

#### Scenario: 双源均失败

- **WHEN** 东财与新浪均抛异常/返回空
- **THEN** 系统 SHALL 返回空 DataFrame，SHALL NOT 抛异常（与现状一致）

### Requirement: 回退列名归一化

新浪指数日 K 返回英文小写列（`date`/`open`/`high`/`low`/`close`/`volume`），系统 SHALL 在回退成功后将其重命名为主源同构中文列：`date→日期`、`open→开盘`、`close→收盘`、`high→最高`、`low→最低`、`volume→成交量`；缺失的列（如新浪指数接口无 `amount`/`turnover`）SHALL 省略不造。

- 归一化后的 DataFrame SHALL 按 `日期` 升序排列，并 `tail(days)` 截断为最近 N 个交易日（与主源路径一致）。

#### Scenario: 回退列重命名

- **WHEN** 新浪返回含 `date`/`close` 两列的 DataFrame
- **THEN** 回退输出 SHALL 含 `日期`/`收盘` 列，且 `收盘` 数值与新浪 `close` 一致

### Requirement: 指数代码新浪符号映射

系统 SHALL 将指数代码映射为新浪符号用于回退调用：上证系列（`000300` 沪深 300、`000001` 上证指数等）→ `sh{code}`，深证系列（`399001` 深证成指、`399006` 创业板指）→ `sz{code}`。

#### Scenario: 沪深 300 转新浪符号

- **WHEN** 传入 `000300`
- **THEN** SHALL 得到 `sh000300`

#### Scenario: 深证指数转新浪符号

- **WHEN** 传入 `399001`
- **THEN** SHALL 得到 `sz399001`

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

