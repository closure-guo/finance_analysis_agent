"""check_cache: 查缓存，返回 HIT / MISS。

HIT = 分析所需核心数据全部缓存命中且未过期：三大报表 + 行业归属 +
行情 + K线 + 基准 + 宏观 + 新闻。
MISS = 任一 key 缺失或过期。

修复（2026-09-08 二轮审计）：此前 HIT 判定只含 5 key（报表/行业/行情），
命中即跳过 fetch_data——但 kline/benchmark_kline/macro_indicators/news_list
不在判定也不附带，同股 24h 内复析会得到技术面/宏观/舆情全缺的残缺报告。
HIT 语义 =「分析所需核心数据完整可用」，故时效性核心数据任一缺失即 MISS，
全部命中时 SHALL 附带完整数据（含永久缓存的 quarterly_income）。

TTL 策略（ADR-0004 + 收窄）：
- 三大报表：30 天（2026-09-08 收窄——此前永久，财报季 staleness 理论窗口
  依赖 quote 1 天 TTL 间接触发刷新；收窄后显式覆盖财报季间隔）
- 行业归属：30 天
- 行情数据 / 行业 PE：1 天
- K线 / 基准 / 新闻：1 小时
- 宏观：1 天
- 预计算指标：同三大报表（30 天）
"""

from __future__ import annotations

from finance_agent.data.cache import DataCache, get_shared_cache


def _get_cache(cache: DataCache | None = None) -> DataCache:
    if cache is not None:
        return cache
    # 2026-09-08 统一：与 nodes/fetch 共用进程级单例（此前两模块各自实例，
    # 两个 Connection 指向同一 cache.db，加倍并发冲突面且语义分裂）
    return get_shared_cache()


def check_cache(state: dict, cache=None) -> dict:
    code = state.get("stock_code", "")
    c = _get_cache(cache)

    keys = [
        f"{code}:balance_sheet",
        f"{code}:income_statement",
        f"{code}:cash_flow_statement",
        f"{code}:industry_info",
        f"{code}:stock_quote",
        # 时效性核心数据（2026-09-08 补入 HIT 判定）：任一缺失/过期 → MISS，
        # 否则同股复析跳过 fetch_data 会得到技术面/宏观/舆情全缺的残缺报告。
        f"{code}:kline",
        "benchmark_kline",
        "macro_indicators",
        f"{code}:news",
    ]

    cached = {}
    for key in keys:
        val = c.get(key)
        if val is None:
            return {"cache_result": "MISS"}
        cached[key] = val

    result = {
        "cache_result": "HIT",
        "balance_sheet": cached[f"{code}:balance_sheet"],
        "income_statement": cached[f"{code}:income_statement"],
        "cash_flow_statement": cached[f"{code}:cash_flow_statement"],
        "industry_info": cached.get(f"{code}:industry_info", {}),
        "stock_quote": cached.get(f"{code}:stock_quote", {}),
        # 时效性核心数据随 HIT 附带（此前全部缺失）
        "kline": cached[f"{code}:kline"],
        "benchmark_kline": cached["benchmark_kline"],
        "macro_indicators": cached["macro_indicators"],
        "news_list": cached[f"{code}:news"],
    }

    # 预计算指标和 industry_pe 有则附带（无则 MISS 时重拉）
    indicators = c.get(f"{code}:indicators")
    if indicators is not None:
        result["financial_indicators"] = indicators
    industry_pe = c.get(f"{code}:industry_pe")
    if industry_pe is not None:
        result["industry_pe"] = industry_pe

    # key_events 有则附带
    key_events = c.get(f"{code}:key_events")
    if key_events is not None:
        result["key_events"] = key_events

    # 季度利润（永久缓存）有则附带
    quarterly_income = c.get(f"{code}:quarterly_income")
    if quarterly_income is not None:
        result["quarterly_income"] = quarterly_income

    return result
