"""指标词表与期次/数值归一化（harden-citation-semantic-coverage delta）。

术语一致性校验的词表来源：metrics/ 注册表键（规范键）+ 中英文别名映射。
注意边界：本模块只服务 metric_name 术语核对与 period 期次核对，
SHALL NOT 用于 field_ref 路径解析（「单一词表」契约：解析层不认中文映射）。
"""

from __future__ import annotations

import re

# 规范键 → 别名列表（含规范键自身小写形式）。比较统一走 lower()。
_METRIC_ALIASES: dict[str, list[str]] = {
    # profitability_metrics
    "ROE": ["roe", "净资产收益率"],
    "ROA": ["roa", "总资产收益率"],
    "ROIC": ["roic", "投入资本回报率"],
    "毛利率": ["毛利率", "gross_margin", "gross margin", "销售毛利率"],
    "净利率": ["净利率", "net_margin", "net margin", "净利润率", "销售净利率"],
    # solvency_metrics
    "资产负债率": ["资产负债率", "负债率", "debt_ratio", "debt ratio", "杠杆率"],
    "流动比率": ["流动比率", "current_ratio", "current ratio"],
    "速动比率": ["速动比率", "quick_ratio", "quick ratio"],
    "利息覆盖倍数": ["利息覆盖倍数", "利息保障倍数", "interest_coverage", "interest coverage"],
    "净债务/EBITDA": ["净债务/ebitda", "net_debt_ebitda", "net debt/ebitda"],
    # efficiency_metrics
    "存货周转率": ["存货周转率", "inventory_turnover", "inventory turnover"],
    "应收账款周转率": ["应收账款周转率", "receivables_turnover", "receivables turnover"],
    "应付账款周转率": ["应付账款周转率", "payables_turnover", "payables turnover"],
    "总资产周转率": ["总资产周转率", "total_asset_turnover", "total asset turnover"],
    # cashflow_metrics
    "经营现金流/净利润": ["经营现金流/净利润", "经营现金流净利润比", "ocf_to_profit"],
    "FCF": ["fcf", "自由现金流"],
    "FCF收益率": ["fcf收益率", "fcf_yield", "fcf yield"],
    "现金流覆盖比率": ["现金流覆盖比率"],
    "留存现金流比率": ["留存现金流比率"],
    "资本支出/折旧": ["资本支出/折旧"],
    # dupont_tree
    "权益乘数": ["权益乘数", "equity_multiplier", "equity multiplier"],
    # technical_indicators
    "MA": ["ma", "均线", "移动平均", "ma5", "ma10", "ma20", "ma60"],
    "MACD": ["macd", "指数平滑异同移动平均线"],
    "DIF": ["dif"],
    "DEA": ["dea"],
    "RSI": ["rsi", "相对强弱指数", "相对强弱指标"],
    "BOLL": ["boll", "布林带", "布林线", "bollinger"],
    "KDJ": ["kdj", "随机指标"],
    # risk_metrics
    "max_drawdown": ["max_drawdown", "最大回撤"],
    "volatility": ["volatility", "波动率"],
    "beta": ["beta", "贝塔"],
    "var_95": ["var_95", "var", "在险价值"],
    # macro_indicators
    "cpi": ["cpi", "居民消费价格指数", "通胀率"],
    "pmi": ["pmi", "采购经理指数", "制造业pmi"],
    "m2": ["m2", "广义货币供应量", "广义货币"],
    "lpr": ["lpr", "贷款市场报价利率"],
    # quarterly_trend
    "yoy": ["yoy", "同比", "同比增速"],
    # 报表常用行（field_ref 指标段即列名，别名收敛到真实列名）
    "营业总收入": ["营业总收入", "营业收入", "营收", "总收入", "revenue"],
    "净利润": ["净利润", "net_profit", "net profit"],
    "归母净利润": ["归母净利润", "归属母公司净利润", "归母净利润(单季)"],
}

_ALIAS_TO_CANONICAL: dict[str, str] = {
    alias.lower(): canonical for canonical, aliases in _METRIC_ALIASES.items() for alias in aliases
}

# 期次形态：年（2024）、报告日（20251231）、ISO 日期（2026-08-28）、季度（2025Q2）
_PERIOD_PATTERNS = [
    re.compile(r"^(19|20)\d{2}$"),
    re.compile(r"^(19|20)\d{2}[01]\d[0-3]\d$"),
    re.compile(r"^(19|20)\d{2}-\d{2}-\d{2}$"),
    re.compile(r"^(19|20)\d{2}[Qq][1-4]$"),
]
_INT_SEGMENT = re.compile(r"^-?\d+$")


def canonical_metric(name: str | None) -> str | None:
    """别名 → 规范键；None/空串/未收录返回 None。"""
    if not name:
        return None
    return _ALIAS_TO_CANONICAL.get(name.strip().lower())


def _is_period_segment(seg: str) -> bool:
    return any(p.match(seg) for p in _PERIOD_PATTERNS)


def field_ref_metric_segments(field_ref: str) -> list[str]:
    """field_ref 的指标段：去根键、去期次段、去纯整数段（索引/参数）。

    例：profitability_metrics.毛利率.2024 → [毛利率]；
    technical_indicators.MA.5.-1 → [MA]；
    macro_indicators.cpi.0.全国-同比增长 → [cpi, 全国-同比增长]。
    """
    parts = field_ref.split(".")
    out: list[str] = []
    for seg in parts[1:]:
        base = re.sub(r"\[(-?\d+)\]$", "", seg)  # yoy[1] → yoy
        if not base:
            continue
        if _is_period_segment(base) or _INT_SEGMENT.match(base):
            continue
        out.append(base)
    return out


def field_ref_period_segment(field_ref: str) -> str | None:
    """首个期次形态段；无则 None（如索引锚定的序列引用）。"""
    for seg in field_ref.split("."):
        base = re.sub(r"\[(-?\d+)\]$", "", seg)
        if _is_period_segment(base):
            return base
    return None


_QUARTER_CN = {"一": "1", "二": "2", "三": "3", "四": "4"}


def normalize_period(period: str) -> str | None:
    """期次表述归一化：年→YYYY，季度→YYYYQn，日期→YYYY-MM-DD，月份→YYYY-MM。"""
    text = period.strip()
    if not text:
        return None
    m = re.match(r"^((?:19|20)\d{2})年?([一二三四])季度$", text)
    if m:
        return f"{m.group(1)}Q{_QUARTER_CN[m.group(2)]}"
    m = re.match(r"^((?:19|20)\d{2})[Qq]([1-4])季?度?$", text)
    if m:
        return f"{m.group(1)}Q{m.group(2)}"
    m = re.match(r"^((?:19|20)\d{2})年(\d{1,2})月(?:份)?$", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.match(r"^((?:19|20)\d{2})[-/](\d{1,2})[-/](\d{1,2})日?$", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"^((?:19|20)\d{2})(\d{2})(\d{2})$", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"^((?:19|20)\d{2})[-/](\d{1,2})$", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.match(r"^((?:19|20)\d{2})(?:年|年报|年度)?$", text)
    if m:
        return m.group(1)
    return None


def period_matches(declared: str, actual: str) -> bool:
    """归一化后相等或互为前缀（年 ⊂ 年月 ⊂ 年月日 视为一致）。

    declared/actual 任一侧无法归一化 → False（调用方按缺口或 FAIL 裁决）。
    """
    d, a = normalize_period(declared), normalize_period(actual)
    if d is None or a is None:
        return False
    if d == a:
        return True
    # 季度只与季度比；年/月/日按连字符前缀逐级包含
    if ("Q" in d) != ("Q" in a):
        return False
    if "Q" in d:
        return False  # 季度已判等，不等即不一致（2025 ≠ 2025Q2：粒度不同判不一致）
    return d.startswith(a) or a.startswith(d)
