"""report_ready SSE 事件载荷契约测试（update-file-export-entry Task 1）。"""

from finance_agent.api import _report_ready_event


def test_report_ready_event_contains_stock_code_and_preserves_fields():
    ev = _report_ready_event(
        "a1",
        "s1",
        "# 报告",
        {"k": 1},
        {"docx": "/tmp/a.docx"},  # noqa: S108  fixture 值非真实临时文件
        "600519",
        "贵州茅台",
        1234,
    )
    assert ev["type"] == "report_ready"
    assert ev["stock_code"] == "600519"
    assert ev["stock_name"] == "贵州茅台"
    assert ev["report_markdown"] == "# 报告"
    assert ev["chart_data"] == {"k": 1}
    assert ev["file_paths"] == {"docx": "/tmp/a.docx"}  # noqa: S108  fixture 值非真实临时文件
    assert ev["duration_ms"] == 1234
    assert ev["timestamp"]
