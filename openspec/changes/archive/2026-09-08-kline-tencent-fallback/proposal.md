# Proposal: kline-tencent-fallback

## Why

个股日 K 线 `fetch_kline` 现有两级：东财 `stock_zh_a_hist` → 新浪 `stock_zh_a_daily`（回退）。实测东财 TLS 风控间歇性封锁（ConnectionError），新浪偶发同样不稳；当双源同时失败时返回空 DataFrame → 技术面数据缺失（近期反馈「技术面缺失」的直接数据层原因之一）。腾讯 `stock_zh_a_hist_tx` 实测始终可用（独立链路），作为**第三级回退**可显著提高 kline 可用率。

## What Changes

- `fetch_kline` 增加腾讯 `stock_zh_a_hist_tx` 第三级回退：新浪失败后调用，`_to_sina_symbol` 前缀（sh/sz）复用，`adjust="qfq"`，返回列按既有 rename_map 归一化为中文列（date→日期/open→开盘/close→收盘/high→最高/low→最低/volume→成交量/amount→成交额/turnover→换手率），升序 + tail(days)。
- 三级优先级：东财 → 新浪 → 腾讯；任一成功即返回，全部失败返回空 DataFrame（现状语义）。
- 不改变主源可用时的行为与列结构。

## Capabilities

### Modified Capabilities

- `data-source-resilience`: 扩展「回退契约」——个股日 K 线 SHALL 三级回退（东财/新浪/腾讯），列名统一归一化。

## Impact

- **代码**: `src/finance_agent/data/akshare_client.py` — `fetch_kline` 补腾讯回退分支（复用 rename_map）。
- **测试**: `tests/data/test_akshare_client.py` — 增腾讯回退用例（东财+新浪均失败→腾讯，列归一化）。
- **行为**: 主源可用零变化；双源失败时多一次腾讯调用不再返回空。
- **契约**: `openspec/specs/data-source-resilience/spec.md` 经 delta 修改。