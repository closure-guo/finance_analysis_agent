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

### Requirement: 行情 quote 三级回退（腾讯单标的 / 东财 spot / 百度估值+腾讯日线）

系统在获取个股行情（`fetch_stock_quote`）时 SHALL 按优先级获取：腾讯 `qt.gtimg.cn` 单标的直查（主源，1 请求/标的）→ 东方财富 `stock_zh_a_spot_em`（第一回退，仅主源失败时触发）→ 百度估值 `stock_zh_valuation_baidu` 总市值/市净率 + 腾讯 `stock_zh_a_hist_tx` 最新收盘价（第二回退）→ 仅名称 fallback（保底）。任一有值字段 SHALL 并入 result，MUST NOT 覆盖高优先级源已有字段。

- 腾讯主源（`_fetch_tencent_quote`）SHALL 直查 `qt.gtimg.cn/q={symbol}`（`_to_sina_symbol` 前缀，GBK 解码，`~` 分隔字段），并映射：最新价 → `price`、涨跌幅、最高、最低、换手率；总市值（单位：亿）→ `market_cap`（×1e8 归一到元，与 quote 层统一元契约对齐）；流通市值（单位：亿）→ 归一到元；市净率 → `PB`。
- 腾讯市盈率字段（实测 TTM 口径）MUST NOT 进入 quote 输出：PE 语义依赖财务口径，quote 层不推导、不透传，下游 compute 按 valuation-signal-integrity 规范以 `derived_ttm` 口径推导（该契约不变）。
- 腾讯主源解析失败、超时或关键字段（`price`/`market_cap`）均缺失时 SHALL 视为主源失败进入第一回退，MUST NOT 抛异常中断。
- 主源成功但部分非关键字段缺失时 SHALL 输出其余字段，缺失字段由下游既有守卫跳过。
- 东财回退路径 SHALL 保留 `_quote_from_spot_df` 映射与 market_cap 单位归一（元），其双源形单测 SHALL 继续生效；全市场 spot 翻页 MUST 仅在腾讯主源失败时发生。
- `sources_seen` 标注 SHALL 如实记录命中源：主源记 `tencent`，回退分别记 `eastmoney` / `baidu`+`tencent`（沿用既有 bucket 命名）。
- 全部源失败仅剩名称时保留 ERROR 日志（维度缺失可观测）。

#### Scenario: 腾讯主源正常直接返回

- **WHEN** `fetch_stock_quote("688072")` 且 `qt.gtimg.cn` 返回完整字段串
- **THEN** 系统 SHALL 直接返回含 `price`/`market_cap`/`PB` 的 dict，SHALL NOT 调用东财与百度
- **AND** `market_cap` SHALL 等于腾讯总市值字段值（亿）× 1e8（元）

#### Scenario: 腾讯 PE 字段不进入 quote

- **WHEN** 腾讯返回串携带市盈率字段（TTM 口径）
- **THEN** quote 输出 MUST NOT 含 `PE` 键
- **AND** compute SHALL 依既有规则推导 `PE_ttm` 并标注 `derived_ttm` 口径

#### Scenario: 腾讯失败回退东财

- **WHEN** 腾讯直查抛异常或关键字段缺失，且东财 `stock_zh_a_spot_em` 可用
- **THEN** 系统 SHALL 走 `_quote_from_spot_df` 映射返回东财字段（`market_cap` 为元单位）
- **AND** 主源路径 MUST NOT 已触发全市场翻页请求

#### Scenario: 腾讯与东财均失败回退百度+腾讯日线

- **WHEN** 腾讯与东财均失败
- **THEN** 系统 SHALL 调用百度估值取 `market_cap` 与 `PB`（×1e8 归一到元），并调腾讯 `stock_zh_a_hist_tx` 最新收盘为 `price`
- **AND** 百度某指标失败 SHALL NOT 影响其余字段并入，SHALL NOT 抛异常

#### Scenario: 主源部分字段缺失不炸管线

- **WHEN** 腾讯主源返回但个别字段（如换手率）缺失
- **THEN** quote SHALL 输出其余字段，SHALL NOT 抛异常
- **AND** 下游消费守卫按既有缺失语义跳过该字段

