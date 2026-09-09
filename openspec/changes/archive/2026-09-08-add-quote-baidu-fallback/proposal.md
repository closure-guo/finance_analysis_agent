# Proposal: add-quote-baidu-fallback

## Why

`fetch_stock_quote` 主源为东财 `stock_zh_a_spot_em`——2026-09-08 实测被 TLS 风控封锁（ConnectionError 3 次全失败），quote 静默降级为仅名称，**PE/PB/市值/价格全部丢失**。下游相对估值/图表/GARP 维度静默跳过，基本面报告只能以推断表述"PE 不低于行业平均"。百度估值接口实测可用（总市值 0.6s / 市净率 0.5s），腾讯日线可用（0.6s，已有 kline fallback 复用）——补二级 fallback 恢复估值与价格维度。

## What Changes

- `fetch_stock_quote` 增加二级 fallback：
  1. **一级（现状）**：东财 `stock_zh_a_spot_em` → 全字段 quote
  2. **二级（新增）**：百度估值 `stock_zh_valuation_baidu`（总市值 + 市净率）→ 补 `market_cap`/`PB`；腾讯 `stock_zh_a_hist_tx` 最新收盘 → 补 `price`
  3. 仍无估值字段时保留既有仅名称 fallback + ERROR 日志（维度缺失可观测）
- PE 不在 quote 内推导（quote 保持纯数据源语义；PE 推导留给下游财务计算），缺失时下游 `or` 守卫照常跳过。
- 不改变主源可用时的行为与返回结构。

## Capabilities

### Modified Capabilities

- `data-source-resilience`: 扩展行情 quote 回退契约——东财失败时 SHALL 尝试百度估值 + 腾讯日线补估值/价格字段。

## Impact

- **代码**: `src/finance_agent/data/akshare_client.py` — `fetch_stock_quote` 加百度/腾讯 fallback 分支。
- **测试**: `tests/data/test_akshare_client.py` — 增百度/腾讯回退用例（东财失败→百度 PB/市值、腾讯价格）。
- **行为**: 主源可用零变化；东财失败时估值/价格维度恢复，不再仅剩名称。
- **契约**: `openspec/specs/data-source-resilience/spec.md` 经 delta 修改。