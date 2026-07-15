"""AKShare API 封装 — 数据拉取 + 年报过滤 + 缺失值处理。

接口：
- fetch_balance_sheet(stock_code, years=5) → DataFrame
- fetch_income_statement(stock_code, years=5) → DataFrame
- fetch_cash_flow(stock_code, years=5) → DataFrame
- fetch_indicators(stock_code, start_year) → DataFrame
- fetch_industry(stock_code) → dict
- fetch_stock_quote(stock_code) → dict
- fetch_peer_data(stock_codes) → DataFrame

数据降级：三大报表缺失 → 抛异常；其他缺失 → 标记 N/A。
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import date, datetime

import akshare as ak
import pandas as pd

logger = logging.getLogger(__name__)

_SINA_MAX_RETRIES = 2
_SINA_RETRY_DELAY = 2
_AK_TIMEOUT = 15  # 单次 AKShare 调用超时秒数


def _call_ak(func, *args, **kwargs):
    """带超时的 AKShare 调用包装。超时返回 None，由调用方处理。"""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=_AK_TIMEOUT)
        except FuturesTimeoutError:
            logger.warning(
                "AKShare 调用超时 (%ds): %s", _AK_TIMEOUT, getattr(func, "__name__", str(func))
            )
            return None


def _sina_report(stock: str, symbol: str) -> pd.DataFrame:
    """Call stock_financial_report_sina with retry - the Sina API is flaky."""
    for attempt in range(1, _SINA_MAX_RETRIES + 1):
        df = _call_ak(ak.stock_financial_report_sina, stock=stock, symbol=symbol)
        if df is not None and not df.empty:
            return df
        logger.warning("Sina API returned empty for %s/%s (attempt %d)", stock, symbol, attempt)
        if attempt < _SINA_MAX_RETRIES:
            time.sleep(_SINA_RETRY_DELAY)
    raise RuntimeError(f"新浪财经接口连续 {_SINA_MAX_RETRIES} 次无响应，请稍后再试")


# AKShare 返回中文列名，下游使用英文 key，在此做映射。
_QUOTE_KEY_MAP = {
    "名称": "name",
    "代码": "code",
    "最新价": "price",
    "总市值": "market_cap",
    "市盈率-动态": "PE",
    "市盈率-静态": "PE_static",
    "市盈率-TTM": "PE_ttm",
    "市净率": "PB",
}

# 行业 PE 接口列名映射
_INDUSTRY_PE_KEY_MAP = {
    "行业名称": "industry_name",
    "静态市盈率-算术平均": "avg_pe",
    "静态市盈率-中位数": "median_pe",
    "静态市盈率-加权平均": "weighted_pe",
    "公司家数": "company_count",
}

_INDUSTRY_KEY_MAP = {
    "公司名称": "name",
    "股票简称": "name",
    "股票名称": "name",
    "公司简称": "name",
    "行业": "industry",
}


def _add_prefix(code: str) -> str:
    """给股票代码加 sh/sz 前缀。"""
    if code.startswith(("sh", "sz")):
        return code
    if code.startswith(("6", "9")):
        return f"sh{code}"
    return f"sz{code}"


class AKShareClient:
    def _filter_annual(self, df: pd.DataFrame) -> pd.DataFrame:
        """只保留年报（报告日以 1231 结尾）。"""
        if df.empty:
            return df
        mask = df["报告日"].astype(str).str.endswith("1231")
        return df[mask].reset_index(drop=True)

    def _normalize_nan(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.where(df.notna(), other=None)  # pyrefly: ignore[no-matching-overload]

    def _check_min_years(self, df: pd.DataFrame, stock_code: str) -> None:
        if len(df) < 2:
            raise ValueError(
                f"股票 {stock_code} 年报数据不足 2 年（当前 {len(df)} 年），至少需要 2 年"
            )

    def _trim_years(self, df: pd.DataFrame, years: int = 5) -> pd.DataFrame:
        return df.head(years)

    def _rename_parent_cols(self, df: pd.DataFrame) -> pd.DataFrame:
        """重命名归母口径列，解决终端编码不一致问题。

         AKShare 返回的中文列名在部分环境中出现编码差异，导致
         row.get('归属于母公司股东的净利润') 返回 None。
        通过列位置定位并统一重命名为标准列名。
        """
        if df.empty:
            return df
        cols = list(df.columns)

        # 利润表：索引 50 = 归属于母公司股东的净利润, 索引 137 = 归属于母公司股东权益合计
        # 资产负债表：索引 137 = 归属于母公司股东权益合计
        # 这些索引基于 AKShare stock_financial_report_sina 的稳定列序
        _rename_map = {
            50: "归母净利润",
            137: "归母所有者权益",
        }
        rename_dict: dict[str, str] = {}
        for idx, new_name in _rename_map.items():
            if idx < len(cols):
                old_name = cols[idx]
                # 仅当该列尚未被重命名时才处理
                if old_name != new_name and new_name not in cols:
                    rename_dict[old_name] = new_name
        if rename_dict:
            df = df.rename(columns=rename_dict)
        return df

    def fetch_balance_sheet(self, stock_code: str, years: int = 5) -> pd.DataFrame:
        stock = _add_prefix(stock_code)
        df = _sina_report(stock, "资产负债表")
        df = self._filter_annual(df)
        df = self._rename_parent_cols(df)
        self._check_min_years(df, stock_code)
        return self._trim_years(df, years)

    def fetch_income_statement(self, stock_code: str, years: int = 5) -> pd.DataFrame:
        stock = _add_prefix(stock_code)
        df = _sina_report(stock, "利润表")
        df = self._filter_annual(df)
        df = self._rename_parent_cols(df)
        self._check_min_years(df, stock_code)
        return self._trim_years(df, years)

    def fetch_cash_flow(self, stock_code: str, years: int = 5) -> pd.DataFrame:
        stock = _add_prefix(stock_code)
        df = _sina_report(stock, "现金流量表")
        df = self._filter_annual(df)
        self._check_min_years(df, stock_code)
        return self._trim_years(df, years)

    def fetch_indicators(self, stock_code: str, start_year: str = "2020") -> pd.DataFrame:
        df = _call_ak(
            ak.stock_financial_analysis_indicator, symbol=stock_code, start_year=start_year
        )
        if df is None or df.empty:
            return pd.DataFrame()
        # 只保留年报（日期以 12-31 结尾）
        if "日期" in df.columns:
            mask = df["日期"].astype(str).str.endswith("12-31")
            df = df[mask].reset_index(drop=True)
        return df

    def _fetch_name_fallback(self, stock_code: str) -> dict:
        """当东方财富接口不可用时，用 stock_info_a_code_name 获取名称。"""
        try:
            df = ak.stock_info_a_code_name()
            row = df[df["code"] == stock_code]
            if not row.empty:
                return {"name": row.iloc[0]["name"]}
        except Exception:
            logger.warning("stock_info_a_code_name fallback failed for %s", stock_code)
        return {}

    def _fetch_industry_cninfo(self, stock_code: str) -> str | None:
        """当东方财富接口不可用时，用 cninfo 获取行业名称（行业中类）。"""
        try:
            df = ak.stock_industry_change_cninfo(symbol=stock_code)
            if not df.empty and "行业中类" in df.columns:
                return str(df.iloc[0]["行业中类"])
        except Exception:
            logger.warning("stock_industry_change_cninfo failed for %s", stock_code)
        return None

    def fetch_industry(self, stock_code: str) -> dict:
        # 主源：东方财富（含行业+名称）
        df = _call_ak(ak.stock_individual_info_em, symbol=stock_code)
        if df is not None and not df.empty:
            result = {}
            for _, row in df.iterrows():
                key = _INDUSTRY_KEY_MAP.get(row["item"], row["item"])
                result[key] = row["value"]
            if result.get("name") or result.get("industry"):
                return result
        # 降级：cninfo 行业 + 名称 fallback
        result = self._fetch_name_fallback(stock_code)
        industry = self._fetch_industry_cninfo(stock_code)
        if industry:
            result["industry"] = industry
        return result

    def fetch_stock_quote(self, stock_code: str) -> dict:
        # 主源：东方财富实时行情（含 PE/PB/市值/价格）
        df = _call_ak(ak.stock_zh_a_spot_em)
        if df is not None and not df.empty:
            # 尝试多种格式匹配（纯数字 / 带前缀）
            for code_key in (stock_code, stock_code.lstrip("sh").lstrip("sz")):
                row = df[df["代码"] == code_key]
                if not row.empty:
                    break
            if not row.empty:
                raw = row.iloc[0].to_dict()
                return {_QUOTE_KEY_MAP.get(k, k): v for k, v in raw.items()}
        # 降级：仅获取名称+代码
        fallback = self._fetch_name_fallback(stock_code)
        if fallback:
            fallback["code"] = stock_code
        return fallback

    def fetch_quarterly_income(self, stock_code: str, quarters: int = 4) -> pd.DataFrame:
        """拉取单季度利润表，计算同比/环比变化率。

        使用 stock_profit_sheet_by_quarterly_em（东方财富），返回数据中的
        PARENT_NETPROFIT 为单季度归母净利润。

        返回列：报告日, 归母净利润(单季), 环比(%), 同比(%)
        """
        # symbol 需要大写 SH/SZ 前缀
        prefix = "SH" if stock_code.startswith(("6", "9")) else "SZ"
        symbol = f"{prefix}{stock_code.lstrip('sh').lstrip('sz')}"

        df = _call_ak(ak.stock_profit_sheet_by_quarterly_em, symbol=symbol)
        if df is None or df.empty or "PARENT_NETPROFIT" not in df.columns:
            raise ValueError(f"股票 {stock_code} 季度利润表数据不可用")

        # 按报告日排序（最新的在前），copy 避免 fragmentation warning
        df = df.sort_values("REPORT_DATE", ascending=False).reset_index(drop=True).copy()

        # 过滤掉未来季度（报告日晚于当前日期）
        from datetime import datetime

        today = datetime.now()
        df["_dt"] = pd.to_datetime(df["REPORT_DATE"])
        df = df[df["_dt"] <= today].reset_index(drop=True)

        # 提取季度标签 (YYYY-Qx)
        def _quarter_label(dt) -> str:
            month = dt.month
            year = dt.year
            q = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}.get(month, "")
            return f"{year}{q}"

        df["季度"] = df["_dt"].apply(_quarter_label)
        df = df[df["季度"] != ""]  # 过滤非季度报告

        # 取最近 N 个季度
        df = df.head(quarters * 2 + 2)  # 多取一些用于计算同比

        # 构建结果
        records = []
        for _i, row in df.iterrows():
            curr_np = row["PARENT_NETPROFIT"]
            if pd.isna(curr_np):
                continue
            qoq = row.get("PARENT_NETPROFIT_QOQ")

            # 计算同比：找去年同期（同季度标签，上一年）
            curr_q = row["季度"]
            curr_year = int(curr_q[:4])
            prev_year_q = f"{curr_year - 1}{curr_q[4:]}"
            prev_rows = df[df["季度"] == prev_year_q]
            yoy = None
            if not prev_rows.empty:
                prev_np = prev_rows.iloc[0]["PARENT_NETPROFIT"]
                if not pd.isna(prev_np) and prev_np != 0:
                    yoy = (float(curr_np) - float(prev_np)) / abs(float(prev_np)) * 100

            records.append(
                {
                    "报告日": str(row["REPORT_DATE"])[:10],
                    "季度": curr_q,
                    "归母净利润(单季)": float(curr_np),
                    "环比": float(qoq) if not pd.isna(qoq) else None,
                    "同比": yoy,
                }
            )

        result = pd.DataFrame(records)
        # 只保留最近 N 个季度
        result = result.head(quarters)
        return self._normalize_nan(result)

    def fetch_industry_pe(self, stock_code: str) -> dict | None:
        """获取个股所属行业的平均静态PE。
        通过 stock_individual_info_em 获取行业名称，再匹配
        stock_industry_pe_ratio_cninfo 的行业PE数据。
        如果任一环节失败返回 None，避免阻塞主流程。
        """
        try:
            # 1. 获取行业名称
            info_df = _call_ak(ak.stock_individual_info_em, symbol=stock_code)
            if info_df is None or info_df.empty:
                return None
            industry_name = None
            for _, row in info_df.iterrows():
                if row["item"] == "行业":
                    industry_name = row["value"]
                    break
            if not industry_name:
                return None

            # 2. 获取全部行业PE（证监会行业分类）
            from datetime import datetime

            date_str = datetime.now().strftime("%Y%m%d")
            pe_df = _call_ak(
                ak.stock_industry_pe_ratio_cninfo, symbol="证监会行业分类", date=date_str
            )
            if pe_df is None or pe_df.empty:
                return None
            # 列名映射
            pe_df = pe_df.rename(columns=_INDUSTRY_PE_KEY_MAP)

            # 3. 模糊匹配行业名称
            matched = pe_df[pe_df["industry_name"].str.contains(industry_name, na=False)]
            if matched.empty:
                return None

            row = matched.iloc[0]
            return {
                "industry_name": row.get("industry_name"),
                "avg_pe": row.get("avg_pe"),
                "median_pe": row.get("median_pe"),
                "weighted_pe": row.get("weighted_pe"),
                "company_count": row.get("company_count"),
            }
        except Exception:
            # 网络异常或 AKShare 接口变更时不阻塞主流程
            return None

    def fetch_kline(self, stock_code: str, days: int = 250) -> pd.DataFrame:
        """拉取个股日 K 线（前复权），返回最近 N 个交易日。

        优先使用 stock_zh_a_hist（东方财富），失败时回退 stock_zh_a_daily（新浪）。
        返回统一中文列名：日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 换手率
        """
        from datetime import datetime, timedelta

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")

        # ── 方案1: 东方财富 stock_zh_a_hist（仅 1 次重试） ──
        df = _call_ak(
            ak.stock_zh_a_hist,
            symbol=stock_code,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
        )
        if df is not None and not df.empty:
            df = df.sort_values("日期").reset_index(drop=True)
            return df.tail(days).reset_index(drop=True)

        # ── 方案2: 新浪 stock_zh_a_daily（回退，仅 1 次重试） ──
        logger.info("东财K线拉取失败，尝试新浪源: %s", stock_code)
        sina_symbol = self._to_sina_symbol(stock_code)
        df = _call_ak(ak.stock_zh_a_daily, symbol=sina_symbol, adjust="qfq")
        if df is not None and not df.empty:
            rename_map = {
                "date": "日期",
                "open": "开盘",
                "close": "收盘",
                "high": "最高",
                "low": "最低",
                "volume": "成交量",
                "amount": "成交额",
                "turnover": "换手率",
            }
            df = df.rename(columns=rename_map)
            df = df.sort_values("日期").reset_index(drop=True)
            return df.tail(days).reset_index(drop=True)

        logger.error("K线拉取均失败: %s", stock_code)
        return pd.DataFrame()

    @staticmethod
    def _to_sina_symbol(stock_code: str) -> str:
        """A 股代码转新浪格式：600519 → sh600519, 000001 → sz000001。"""
        if stock_code.startswith(("6", "9")):
            return f"sh{stock_code}"
        elif stock_code.startswith(("0", "2", "3")):
            return f"sz{stock_code}"
        elif stock_code.startswith(("4", "8")):
            return f"bj{stock_code}"
        return f"sh{stock_code}"

    def fetch_benchmark_kline(self, days: int = 250) -> pd.DataFrame:
        """拉取沪深 300 指数日 K 线，返回最近 N 个交易日。

        使用 index_zh_a_hist（东方财富），返回列含 日期, 收盘 等。
        """
        from datetime import datetime, timedelta

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")

        df = _call_ak(
            ak.index_zh_a_hist,
            symbol="000300",
            period="daily",
            start_date=start_date,
            end_date=end_date,
        )
        if df is None or df.empty:
            logger.warning("沪深300 K线拉取失败或为空")
            return pd.DataFrame()

        df = df.sort_values("日期").reset_index(drop=True)
        return df.tail(days).reset_index(drop=True)

    # ── 宏观指标 ──

    def fetch_macro_indicators(self) -> dict:
        """拉取宏观经济指标：CPI、PMI、M2、LPR。

        返回 dict，每个指标取最近 6 个月数据。
        失败的指标返回空列表，不阻塞流程。
        """
        result: dict[str, list[dict]] = {}

        def _safe_macro(key: str, func):
            df = _call_ak(func)
            if df is not None and not df.empty:
                records = df.tail(6).to_dict(orient="records")
                # 序列化 date/datetime 对象，避免 JSON 编码失败
                for r in records:
                    for k, v in r.items():
                        if isinstance(v, (date, datetime)):
                            r[k] = v.isoformat()
                result[key] = records
            else:
                result[key] = []

        _safe_macro("cpi", ak.macro_china_cpi)
        _safe_macro("pmi", ak.macro_china_pmi)
        _safe_macro("m2", ak.macro_china_money_supply)
        _safe_macro("lpr", ak.macro_china_lpr)

        return result

    # ── 新闻资讯 ──

    def fetch_news(self, stock_code: str, limit: int = 20) -> list[dict]:
        """拉取个股新闻资讯（东方财富）。

        返回 list[dict]，每条含 title、content、datetime、source。
        失败返回空列表。
        """
        df = _call_ak(ak.stock_news_em, symbol=stock_code)
        if df is None or df.empty:
            return []
        df = df.head(limit)
        # 标准化列名
        col_map = {
            "新闻标题": "title",
            "新闻内容": "content",
            "发布时间": "datetime",
            "文章来源": "source",
            "新闻链接": "url",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        records = df.to_dict(orient="records")
        # 序列化 date/datetime 对象
        for r in records:
            for k, v in r.items():
                if isinstance(v, (date, datetime)):
                    r[k] = v.isoformat()
            r.setdefault("title", "")
            r.setdefault("content", "")
            r.setdefault("datetime", "")
            r.setdefault("source", "")
        return records
