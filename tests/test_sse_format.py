"""SSE 帧格式测试：验证 _sse 输出包含 id: 行（当 data 有 seq 字段时）。"""

from finance_agent.api import _sse


def test_sse_with_seq_includes_id_line():
    """data 含 seq 字段时，_sse 输出应包含 id: 行。"""
    data = {"type": "chat_token", "token": "hello", "seq": 42}
    result = _sse(data)
    assert "id: 42\n" in result
    assert "data: " in result
    # id 行在 data 行之前
    assert result.index("id: 42\n") < result.index("data: ")


def test_sse_without_seq_excludes_id_line():
    """data 无 seq 字段时，_sse 输出不应包含 id: 行。"""
    data = {"type": "chat_token", "token": "hello"}
    result = _sse(data)
    assert "id:" not in result
    assert "data: " in result


def test_sse_seq_none_excludes_id_line():
    """data 的 seq 为 None 时，_sse 输出不应包含 id: 行。"""
    data = {"type": "chat_token", "token": "hello", "seq": None}
    result = _sse(data)
    assert "id:" not in result
