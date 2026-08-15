"""确定性评估器:零 token、可重算、可进 CI(spec Requirement「确定性评估器」)。"""

from __future__ import annotations

from evals.sections import find_section


def section_coverage(report: str | None, expected_output: dict) -> dict | None:
    """必备章节覆盖率。expected 无 must_cover 时返回 None(不计入该维度)。"""
    must_cover = expected_output.get("must_cover")
    if not must_cover:
        return None
    if report is None:
        return {"name": "section_coverage", "value": 0.0, "comment": "无报告产出"}
    missing = [s for s in must_cover if not find_section(s, report)]
    value = (len(must_cover) - len(missing)) / len(must_cover)
    return {
        "name": "section_coverage",
        "value": round(value, 4),
        "comment": f"缺失章节: {', '.join(missing)}" if missing else None,
    }


def ticker_match(ticker: str | None, expected_output: dict) -> dict | None:
    """标的解析正确性。expected 无 ticker 时返回 None。"""
    expected_ticker = expected_output.get("ticker")
    if not expected_ticker:
        return None
    if ticker is None:
        return {"name": "ticker_match", "value": 0.0, "comment": "未解析出标的"}
    matched = ticker == expected_ticker
    return {
        "name": "ticker_match",
        "value": 1.0 if matched else 0.0,
        "comment": None if matched else f"期望 {expected_ticker},实际 {ticker}",
    }


def make_evaluation(result: dict):
    """评估结果 dict → langfuse Evaluation(langfuse 4.13 experiment API)。

    value 为 float;comment 可为 None。langfuse 未配置环境不会走到这里
    (--local 模式直接消费 dict)。
    """
    from langfuse.experiment import Evaluation

    return Evaluation(name=result["name"], value=result["value"], comment=result.get("comment"))
