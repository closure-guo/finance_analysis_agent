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

import akshare as ak
import pandas as pd

logger = logging.getLogger(__name__)

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

    def fetch_balance_sheet(self, stock_code: str, years: int = 5) -> pd.DataFrame:
        stock = _add_prefix(stock_code)
        df = ak.stock_financial_report_sina(stock=stock, symbol="资产负债表")
        df = self._filter_annual(df)
        self._check_min_years(df, stock_code)
        return self._trim_years(df, years)

    def fetch_income_statement(self, stock_code: str, years: int = 5) -> pd.DataFrame:
        stock = _add_prefix(stock_code)
        df = ak.stock_financial_report_sina(stock=stock, symbol="利润表")
        df = self._filter_annual(df)
        self._check_min_years(df, stock_code)
        return self._trim_years(df, years)

    def fetch_cash_flow(self, stock_code: str, years: int = 5) -> pd.DataFrame:
        stock = _add_prefix(stock_code)
        df = ak.stock_financial_report_sina(stock=stock, symbol="现金流量表")
        df = self._filter_annual(df)
        self._check_min_years(df, stock_code)
        return self._trim_years(df, years)

    def fetch_indicators(self, stock_code: str, start_year: str = "2020") -> pd.DataFrame:
        df = ak.stock_financial_analysis_indicator(symbol=stock_code, start_year=start_year)
        # 只保留年报（日期以 12-31 结尾）
        if not df.empty and "日期" in df.columns:
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
        try:
            df = ak.stock_individual_info_em(symbol=stock_code)
            result = {}
            for _, row in df.iterrows():
                key = _INDUSTRY_KEY_MAP.get(row["item"], row["item"])
                result[key] = row["value"]
            if result.get("name") or result.get("industry"):
                return result
        except Exception as e:
            logger.warning("stock_individual_info_em failed for %s: %s", stock_code, e)
        # 降级：cninfo 行业 + 名称 fallback
        result = self._fetch_name_fallback(stock_code)
        industry = self._fetch_industry_cninfo(stock_code)
        if industry:
            result["industry"] = industry
        return result

    def fetch_stock_quote(self, stock_code: str) -> dict:
        # 主源：东方财富实时行情（含 PE/PB/市值/价格）
        try:
            df = ak.stock_zh_a_spot_em()
            # 尝试多种格式匹配（纯数字 / 带前缀）
            for code_key in (stock_code, stock_code.lstrip("sh").lstrip("sz")):
                row = df[df["代码"] == code_key]
                if not row.empty:
                    break
            if not row.empty:
                raw = row.iloc[0].to_dict()
                return {_QUOTE_KEY_MAP.get(k, k): v for k, v in raw.items()}
        except Exception as e:
            logger.warning("stock_zh_a_spot_em failed for %s: %s", stock_code, e)
        # 降级：仅获取名称+代码
        fallback = self._fetch_name_fallback(stock_code)
        if fallback:
            fallback["code"] = stock_code
        return fallback

    def fetch_industry_pe(self, stock_code: str) -> dict | None:
        """获取个股所属行业的平均静态PE。

        通过 stock_individual_info_em 获取行业名称，再匹配
        stock_industry_pe_ratio_cninfo 的行业PE数据。
        如果任一环节失败返回 None，避免阻塞主流程。
        """
        try:
            # 1. 获取行业名称
            info_df = ak.stock_individual_info_em(symbol=stock_code)
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
            pe_df = ak.stock_industry_pe_ratio_cninfo(symbol="证监会行业分类", date=date_str)
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
