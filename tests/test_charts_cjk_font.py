"""复现缺陷：Docker 容器（python:3.12-slim）内无任何中文字体，charts.py 的
font.sans-serif 回退链（Microsoft YaHei / SimHei / Arial Unicode MS / Arial）
全部 miss，matplotlib 静默回退到 DejaVu Sans，导致报告 PNG 中所有汉字渲染为
豆腐块（□）。

测试断言：回退链中至少一个字体在当前运行环境真实可解析，且解析结果不是
matplotlib 的兜底字体 DejaVu Sans。
"""

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt


def test_sans_serif_fallback_chain_resolves_to_cjk_capable_font():
    """charts.py 配置的 sans-serif 回退链须在本环境命中真实字体。

    在缺 CJK 字体的 Linux 容器里，链上四个名字一个都找不到，
    findfont 会静默回退到 DejaVu Sans（不含 CJK 字形）——即本 bug。
    """
    # 延迟导入，确保拿到 charts.py 设置后的 rcParams
    import finance_agent.charts  # noqa: F401

    chain = plt.rcParams["font.sans-serif"]
    resolved = fm.findfont(
        fm.FontProperties(family=chain),
        fallback_to_default=False,
    )
    assert resolved is not None, (
        f"sans-serif 回退链 {chain} 在当前环境全部 miss，"
        "图表中文将渲染为豆腐块；需在环境中安装 CJK 字体（如 fonts-noto-cjk）"
        "并把对应字体名加入回退链"
    )


def test_resolved_sans_serif_font_supports_cjk_glyph():
    """回退链解析出的字体文件须包含 CJK 字形（以「中」字为探针）。"""
    from fontTools.ttLib import TTFont

    import finance_agent.charts  # noqa: F401

    chain = plt.rcParams["font.sans-serif"]
    font_path = fm.findfont(fm.FontProperties(family=chain))
    font = TTFont(font_path, fontNumber=0)
    cmap = font.getBestCmap()
    assert ord("中") in cmap, (
        f"回退链解析到 {font_path}，但该字体不含 CJK 字形，中文仍会显示为豆腐块"
    )
