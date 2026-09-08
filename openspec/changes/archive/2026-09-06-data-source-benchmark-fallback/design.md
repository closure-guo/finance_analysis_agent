# Design: data-source-benchmark-fallback

## 现状

`fetch_index_kline(index_code, days)`（`src/finance_agent/data/akshare_client.py:454`）：

1. 计算 start_date = 今天 - 2×days，end_date = 今天
2. 调 `_call_ak(ak.index_zh_a_hist, symbol=index_code, period="daily", start_date, end_date)`（东财，3 次重试）
3. 空/异常 → WARN + 返回空 DataFrame

下游消费（全部只依赖 `日期` + `收盘` 两列）：

- `metrics/risk.py:calc_risk` — `benchmark_kline["收盘"]`（Beta）
- `outcome/job.py:_is_stale` — `benchmark["日期"]` 字符串比较
- `outcome/track_record/marking.py:_bench_by_date` — `zip(benchmark["日期"], benchmark["收盘"])`
- `outcome/track_record/segments.py:market_env_signal` — 收盘序列

## 方案：复用 fetch_kline 的「东财 → 新浪」回退模式

```
fetch_index_kline(index_code, days):
    df = _call_ak(ak.index_zh_a_hist, ...)          # 主源（东财）
    if df 非空: return 升序 + tail(days)             # 主源优先，零行为变化

    # 回退：新浪指数日 K
    sina_symbol = _to_sina_symbol(index_code)        # 000300 → sh000300
    df = _call_ak(ak.stock_zh_index_daily, symbol=sina_symbol)
    if df 非空:
        df = df.rename(columns={date→日期, open→开盘, close→收盘,
                                high→最高, low→最低, volume→成交量})
        return 升序 + tail(days)
    return pd.DataFrame()                            # 双源均失败
```

### 符号映射

新浪指数符号：`sh000300`（沪）、`sz399001`（深）。指数代码 `000300` 以 `0` 开头，若复用既有 `_to_sina_symbol` 会得到 `sz000300`（错）。因此需要指数特判：

- `index_code` 以 `399` 开头 → `sz`（深证系列：399001 深证成指、399006 创业板指）
- 其余（`000` 开头的上证系列，如 000300/000001 上证指数/000905 中证 500）→ `sh`

实现上，`_to_sina_symbol` 保持股票语义不变；`fetch_index_kline` 内做指数特判（不污染股票路径），或新增 `_to_sina_index_symbol` 私有函数。选择后者（语义清晰、可单测）。

### 列归一化

新浪 `stock_zh_index_daily` 返回：`date, open, high, low, close, volume`（无 amount/turnover）。rename_map 复用 `fetch_kline` 的子集，缺失列省略。下游只读 `日期`/`收盘`，其余列仅作同构保留（升序排序依赖 `日期`）。

### 边界

- 主源可用：零行为变化（不触发回退，无额外调用）。
- 双源失败：返回空 DataFrame（现状语义），不抛异常。
- 排序一致性：回退路径也 `sort_values("日期")` + `tail(days)`，与主源一致。
- 性能：仅回退路径多发一次请求，主源路径零开销。
