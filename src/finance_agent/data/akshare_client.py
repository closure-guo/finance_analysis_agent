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

import akshare as ak
import pandas as pd


# AKShare 返回中文列名，下游使用英文 key，在此做映射。
_QUOTE_KEY_MAP = {
    "名称": "name",
    "代码": "code",
    "最新价": "price",
    "总市值": "market_cap",
    "市盈率-动态": "PE",
    "市净率": "PB",
}

_INDUSTRY_KEY_MAP = {
    "公司名称": "name",
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
        return df.where(df.notna(), other=None)

    def _check_min_years(self, df: pd.DataFrame, stock_code: str) -> None:
        if len(df) < 2:
            raise ValueError(
                f"股票 {stock_code} 年报数据不足 2 年（当前 {len(df)} 年），至少需要 2 年"
            )

    def _trim_years(self, df: pd.DataFrame, years: int = 5) -> pd.DataFrame:
        return df.head(years)

    def fetch_balance_sheet(
        self, stock_code: str, years: int = 5
    ) -> pd.DataFrame:
        stock = _add_prefix(stock_code)
        df = ak.stock_financial_report_sina(stock=stock, symbol="资产负债表")
        df = self._filter_annual(df)
        self._check_min_years(df, stock_code)
        return self._trim_years(df, years)

    def fetch_income_statement(
        self, stock_code: str, years: int = 5
    ) -> pd.DataFrame:
        stock = _add_prefix(stock_code)
        df = ak.stock_financial_report_sina(stock=stock, symbol="利润表")
        df = self._filter_annual(df)
        self._check_min_years(df, stock_code)
        return self._trim_years(df, years)

    def fetch_cash_flow(
        self, stock_code: str, years: int = 5
    ) -> pd.DataFrame:
        stock = _add_prefix(stock_code)
        df = ak.stock_financial_report_sina(stock=stock, symbol="现金流量表")
        df = self._filter_annual(df)
        self._check_min_years(df, stock_code)
        return self._trim_years(df, years)

    def fetch_indicators(self, stock_code: str, start_year: str = "2020") -> pd.DataFrame:
        df = ak.stock_financial_analysis_indicator(
            symbol=stock_code, start_year=start_year
        )
        # 只保留年报（日期以 12-31 结尾）
        if not df.empty and "日期" in df.columns:
            mask = df["日期"].astype(str).str.endswith("12-31")
            df = df[mask].reset_index(drop=True)
        return df

    def fetch_industry(self, stock_code: str) -> dict:
        df = ak.stock_individual_info_em(symbol=stock_code)
        result = {}
        for _, row in df.iterrows():
            key = _INDUSTRY_KEY_MAP.get(row["item"], row["item"])
            result[key] = row["value"]
        return result

    def fetch_stock_quote(self, stock_code: str) -> dict:
        df = ak.stock_zh_a_spot_em()
        row = df[df["代码"] == stock_code]
        if row.empty:
            return {}
        raw = row.iloc[0].to_dict()
        return {_QUOTE_KEY_MAP.get(k, k): v for k, v in raw.items()}
