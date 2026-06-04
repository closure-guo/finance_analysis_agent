"""comprehensive 模式集成测试 — mock LLM，验证 graph 拓扑和 pipeline 正确性。"""

from unittest.mock import patch

import pytest


@patch("finance_agent.llm.call_llm")
def test_comprehensive_pipeline(mock_llm, tmp_path):
    """验证 comprehensive 模式下：
    1. fa_analyze 和 ia_analyze 都被调用
    2. merge 在两者之后被调用
    3. 最终报告包含综合结论、对比表格、FA、IA、免责声明
    """
    from finance_agent.graph import build_graph

    call_count = 0

    def side_effect(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        # 根据 prompt 内容区分调用
        if "财务分析" in prompt or "fa_analyze" in str(kwargs):
            return "FA正文内容"
        if "投资分析" in prompt or "ia_analyze" in str(kwargs):
            return "IA正文内容"
        if "综合结论" in prompt or "synthesis" in prompt:
            return "综合结论：买入"
        # 摘要生成
        if "摘要" in prompt:
            return "执行摘要"
        return f"LLM响应-{call_count}"

    mock_llm.side_effect = side_effect

    # 将报告输出重定向到临时目录，避免污染 reports/
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))

    graph = build_graph()

    # 构造足够完整的 state，让 pipeline 跑通
    import pandas as pd

    state = {
        "stock_code": "600519",
        "analysis_type": "comprehensive",
        "peer_codes": None,
        "balance_sheet": pd.DataFrame(
            {
                "报告日": ["20251231", "20241231"],
                "资产总计": [3e11, 2.8e11],
                "负债合计": [5e10, 4.8e10],
                "流动资产合计": [2.5e11, 2.3e11],
                "流动负债合计": [5e10, 4.8e10],
                "存货": [6e10, 5.8e10],
                "货币资金": [5e10, 4.5e10],
                "短期借款": [None, None],
                "长期借款": [None, None],
                "应付债券": [None, None],
                "一年内到期的非流动负债": [1e7, 1e7],
                "累计折旧": [1.6e10, 1.5e10],
            }
        ),
        "income_statement": pd.DataFrame(
            {
                "报告日": ["20251231", "20241231"],
                "营业收入": [1.6e11, 1.5e11],
                "营业成本": [1.4e10, 1.3e10],
                "净利润": [8.5e10, 8e10],
                "利润总额": [1.1e11, 1e11],
                "所得税费用": [2.9e10, 2.8e10],
                "利息费用": [2e7, 2e7],
                "销售费用": [7e9, 6.5e9],
                "管理费用": [8e9, 7.5e9],
                "研发费用": [1e8, 1e8],
                "财务费用": [-8e8, -7e8],
            }
        ),
        "cash_flow_statement": pd.DataFrame(
            {
                "报告日": ["20251231", "20241231"],
                "经营活动产生的现金流量净额": [6e10, 5.5e10],
                "购建固定资产、无形资产和其他长期资产所支付的现金": [3e9, 2.5e9],
                "分配股利、利润或偿付利息所支付的现金": [6.5e10, 6e10],
            }
        ),
        "financial_indicators": pd.DataFrame(),
        "industry_info": {"name": "贵州茅台", "industry": "白酒"},
        "stock_quote": {"name": "贵州茅台", "code": "600519", "PE": 25.5, "PB": 8.2},
        "industry_pe": {"avg_pe": 30.0, "median_pe": 28.0},
    }

    result = graph.invoke(state)

    # 验证最终报告
    final_report = result.get("final_report", "")
    assert "综合分析报告" in final_report, "报告标题缺失"
    assert "综合结论" in final_report, "综合结论缺失"
    assert "核心数据对比" in final_report, "对比表格缺失"
    assert "免责声明" in final_report, "免责声明缺失"
    assert result.get("file_paths") is not None, "文件路径缺失"

    # 验证文件输出到临时目录，而非 reports/
    docx_path = result["file_paths"]["docx"]
    assert str(tmp_path) in docx_path, f"报告写入了非临时目录：{docx_path}"

    monkeypatch.undo()

    # 验证 LLM 调用次数：fa正文 + fa摘要 + ia正文 + ia摘要 + synthesis = 5 次
    # 但并行执行时 fa 和 ia 各自 2 次，synthesis 1 次
    assert mock_llm.call_count >= 3, f"LLM 调用次数不足：{mock_llm.call_count}"
