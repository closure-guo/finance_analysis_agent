"""基准集确定性 state fixture：代码内构建 DataFrame（非二进制存储，可 diff、可审计）。

state_v1 与 tests/conftest.py 同源风格：3 年圆整财务数据 + 80 日合成 K 线。
"""

from __future__ import annotations

import pandas as pd

_BALANCE = pd.DataFrame(
    {
        "报告日": ["20241231", "20231231", "20221231"],
        "货币资金": [200.0, 180.0, 150.0],
        "存货": [100.0, 90.0, 80.0],
        "流动资产合计": [500.0, 450.0, 400.0],
        "固定资产净值": [300.0, 280.0, 260.0],
        "累计折旧": [120.0, 100.0, 80.0],
        "非流动资产合计": [500.0, 450.0, 400.0],
        "资产总计": [1000.0, 900.0, 800.0],
        "短期借款": [80.0, 70.0, 60.0],
        "应付账款": [60.0, 50.0, 45.0],
        "应收账款": [40.0, 35.0, 30.0],
        "一年内到期的非流动负债": [20.0, 15.0, 10.0],
        "流动负债合计": [300.0, 280.0, 260.0],
        "长期借款": [50.0, 40.0, 30.0],
        "应付债券": [30.0, 20.0, 20.0],
        "非流动负债合计": [100.0, 70.0, 60.0],
        "负债合计": [400.0, 350.0, 320.0],
        "所有者权益(或股东权益)合计": [600.0, 550.0, 480.0],
        "实收资本(或股本)": [125.0, 125.0, 125.0],
        "未分配利润": [200.0, 170.0, 140.0],
    }
)

_INCOME = pd.DataFrame(
    {
        "报告日": ["20241231", "20231231", "20221231"],
        "营业收入": [1000.0, 900.0, 800.0],
        "营业成本": [600.0, 550.0, 500.0],
        "销售费用": [50.0, 45.0, 40.0],
        "管理费用": [60.0, 55.0, 50.0],
        "研发费用": [30.0, 25.0, 20.0],
        "财务费用": [22.0, 20.0, 18.0],
        "利息费用": [20.0, 18.0, 16.0],
        "营业利润": [200.0, 180.0, 160.0],
        "利润总额": [200.0, 180.0, 160.0],
        "所得税费用": [30.0, 27.0, 24.0],
        "净利润": [170.0, 153.0, 136.0],
        "归属于母公司所有者的净利润": [168.0, 151.0, 134.0],
    }
)

_CASH = pd.DataFrame(
    {
        "报告日": ["20241231", "20231231", "20221231"],
        "经营活动产生的现金流量净额": [250.0, 220.0, 200.0],
        "购建固定资产、无形资产和其他长期资产所支付的现金": [80.0, 70.0, 60.0],
        "投资活动产生的现金流量净额": [-100.0, -90.0, -80.0],
        "分配股利、利润或偿付利息所支付的现金": [50.0, 45.0, 40.0],
        "筹资活动产生的现金流量净额": [-30.0, -20.0, -10.0],
    }
)


def _kline(n: int = 80) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=n, freq="D").strftime("%Y-%m-%d")
    return pd.DataFrame(
        {
            "日期": dates,
            "开盘": [10.0] * n,
            "收盘": [10.0 + i * 0.1 for i in range(n)],
            "最高": [10.5 + i * 0.1 for i in range(n)],
            "最低": [9.5 + i * 0.1 for i in range(n)],
            "成交量": [1000.0] * n,
        }
    )


def build_state(state_key: str) -> dict:
    if state_key != "state_v1":
        raise KeyError(f"未知 state fixture: {state_key}")
    from finance_agent.metrics.solvency import calc_solvency

    balance_sheet = _BALANCE.copy()
    income_statement = _INCOME.copy()
    base: dict[str, object] = {
        "balance_sheet": balance_sheet,
        "income_statement": income_statement,
        "cash_flow_statement": _CASH.copy(),
        "financial_indicators": None,
        "kline": _kline(),
        "benchmark_kline": _kline(),
    }
    # 数值型 claim 直接读值的派生指标须在 state 中可得（与真实管线 compute 后一致）
    base["solvency_metrics"] = calc_solvency(balance_sheet, income_statement, None)
    return base
