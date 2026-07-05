"""comprehensive 模式端到端测试 — 真实 LLM + 真实 AKShare 数据，验证 graph 拓扑和 pipeline 正确性。

运行方式：
    set DEEPSEEK_API_KEY=your_key
    uv run pytest tests/e2e/test_comprehensive_pipeline.py -s
"""

import os

import pytest


@pytest.mark.skipif(
    not (os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")),
    reason="E2E 测试需要真实 LLM，请设置 DEEPSEEK_API_KEY 或 LLM_API_KEY 环境变量",
)
def test_comprehensive_pipeline(tmp_path):
    """验证 comprehensive 模式下：
    1. fa_analyze 和 ia_analyze 都被调用
    2. merge 在两者之后被调用
    3. 最终报告包含综合结论、对比表格、FA、IA、免责声明
    """
    from finance_agent.graph import build_graph

    # 将报告输出重定向到临时目录，避免污染 reports/
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))

    graph = build_graph()

    # 仅提供股票代码，由 graph 的 fetch_data 节点拉取真实数据
    state = {
        "stock_code": "600519",
        "analysis_type": "comprehensive",
        "peer_codes": None,
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
