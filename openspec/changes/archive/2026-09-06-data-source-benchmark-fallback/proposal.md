# Proposal: data-source-benchmark-fallback

## Why

东财对数据中心 API 的 TLS 指纹风控（连接层 RST）间歇性触发时，`fetch_index_kline`（沪深 300 等指数日 K，用于 `calc_risk` 的 Beta、结算 `benchmark_return`、track-record 盯市基准）**无任何回退**：东财 `index_zh_a_hist` 失败即返回空 DataFrame，导致基准缺失、Beta 无法计算、结算 excess 记 null。

个股 K 线（`fetch_kline`）已有「东财 → 新浪」回退且验证有效（`stock_zh_a_daily`，实测正常），但指数 K 线没有对等回退——这是数据层单点依赖缺口。新浪 `stock_zh_index_daily`（sh000300）实测正常（5986 行、数据至最近交易日）。

## What Changes

- `fetch_index_kline` 增加**新浪 `stock_zh_index_daily` 回退**：东财失败/为空时，按指数代码转新浪符号（`_to_sina_symbol` 扩展支持指数前缀），拉取后统一归一化列名为东财同构中文列（`日期`/`开盘`/`收盘`/`最高`/`最低`/`成交量`），保证下游消费者（`calc_risk` 的 `收盘`、`outcome/job.py` 的 `日期`、track-record 的 `日期`+`收盘`）零改动。
- 指数符号映射：`000300` → `sh000300`、`399001` → `sz399001`、`000001` → `sh000001` 等；扩展 `_to_sina_symbol` 处理指数前缀（不以股票前缀规则误判）。
- **行为契约**：主源可用时行为与现状完全一致；仅主源失败时回退，不改变返回列名与排序（升序 + tail(days)）。

## Capabilities

### New Capabilities

- `data-source-resilience`（新增 spec）：定义关键行情接口（指数 K 线）在主数据源失败时的回退契约——回退源的返回列统一归一化为东财同构中文列，主源可用时行为与回退无关。

### Modified Capabilities

（无）

## Impact

- **代码**:
  - `src/finance_agent/data/akshare_client.py` — `fetch_index_kline` 增加新浪回退分支；`_to_sina_symbol` 支持指数前缀。
  - `tests/data/test_akshare_client.py` — 新增 `fetch_index_kline` 回退单元测试（mock ak）。
- **行为**: 主源可用零变化；主源失败时基准数据不再缺失（Beta/结算/track-record 基准恢复可用）。
- **契约**: 新增 `openspec/specs/data-source-resilience/spec.md`（经 delta 引入）。
- **性能**: 仅回退路径多发一次网络调用；主源路径零额外开销。
