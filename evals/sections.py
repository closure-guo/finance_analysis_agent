"""必备章节同义词词典(design 决策 5:替代裸字符串 in 匹配)。

每个必备章节配一组同义词,命中任一即算覆盖。词典没有的章节名退化为
字面匹配。首版词典按 4 分析师 + 报告骨架的常见章节维护,bad case 驱动追加。
"""

import re

SECTION_SYNONYMS: dict[str, list[str]] = {
    "宏观环境": ["宏观环境", "宏观分析", "宏观经济", "政策面", "宏观"],
    "基本面": ["基本面", "基本面分析", "财务分析", "财务状况", "财务"],
    "偿债能力": ["偿债能力", "偿债分析", "债务分析", "资产负债率", "流动比率", "solvency"],
    "盈利能力": ["盈利能力", "盈利分析", "利润率", "ROE", "毛利率", "profitability"],
    "技术面": ["技术面", "技术分析", "K线", "均线", "走势分析", "趋势"],
    "市场情绪": ["市场情绪", "情绪分析", "资金面", "市场情绪面", "情绪"],
    "估值": ["估值", "估值分析", "估值水平", "PE", "PB", "市盈率"],
    "风险提示": ["风险提示", "风险分析", "风险因素", "风险揭示"],
    "交易建议": ["交易建议", "操作建议", "投资建议", "决策建议", "交易策略"],
}


def _matches(synonym: str, report: str) -> bool:
    """纯 ASCII 词条按 ASCII 词字符环视匹配(避免 PE ⊂ OPENAI/PIPELINE,且 CJK 紧贴仍命中),其余子串匹配。"""
    if synonym.isascii():
        return (
            re.search(r"(?<![A-Za-z0-9_])" + re.escape(synonym) + r"(?![A-Za-z0-9_])", report)
            is not None
        )
    return synonym in report


def find_section(section: str, report: str) -> bool:
    """章节命中判定:同义词词典匹配,未知章节退化为字面匹配。"""
    synonyms = SECTION_SYNONYMS.get(section, [section])
    return any(_matches(s, report) for s in synonyms)
