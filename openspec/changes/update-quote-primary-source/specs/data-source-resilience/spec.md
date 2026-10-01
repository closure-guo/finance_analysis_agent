# Delta for data-source-resilience

## REMOVED Requirements

### Requirement: 行情 quote 二级回退（百度估值 + 腾讯日线）

**Reason**: 主源发生结构性切换——东财 `stock_zh_a_spot_em` 全市场翻页（约 50+ 请求/次拿单只股票）是本机 IP 被东财行情域封禁的直接成因，且该源已不可靠；回退链由二级重构为三级（腾讯单标的主源 → 东财回退 → 百度估值+腾讯日线）。

**Migration**: 由本 delta 的 ADDED Requirement「行情 quote 三级回退（腾讯单标的 / 东财 spot / 百度估值+腾讯日线）」完整承接；百度估值+腾讯日线降级语义原样保留为第二回退，PE 推导留给下游 compute 的 derived_ttm 契约不变（见 valuation-signal-integrity）。

## ADDED Requirements

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
