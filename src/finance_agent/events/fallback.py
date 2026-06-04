"""L3: 兜底事件生成器。"""

from __future__ import annotations


def fallback_annotation() -> list[dict]:
    """返回兜底事件，提示用户事件数据暂时不可用。"""
    return [
        {
            "date": "",
            "type": "数据状态",
            "title": "事件数据暂时不可用",
            "summary": "当前未接入实时事件源，仅展示预构建库数据。如需查看该股票事件，请检查是否支持该股票代码。",
            "impact": "neutral",
            "level": "L1",
            "source": "system",
            "url": None,
            "ongoing": False,
        }
    ]
