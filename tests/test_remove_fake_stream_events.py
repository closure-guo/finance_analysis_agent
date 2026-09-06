"""remove-fake-stream-events 回归测试。

验证 LLM 事件通道不再有系统生成的冒充事件（spec: chat-stream「流式事件真实性」）：
① 预搜索旁路（伪 thinking/tool_call + 用户消息注入）已删除；
② ③ 管线节点开始/完成伪 thinking_token（▶/✓）已删除；
节点真实 thinking 转发（custom mode）保留。
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from finance_agent import api as api_mod
from finance_agent import session_store
from finance_agent.api import AnalyzeRequest


def _sse_events(raw_lines: list[str]) -> list[dict]:
    out = []
    for line in raw_lines:
        if line.startswith("data: "):
            out.append(json.loads(line[len("data: ") :]))
    return out


# ── ① 预搜索旁路删除 ──


@pytest.mark.asyncio
async def test_timesensitive_query_no_presearch_events(tmp_path, monkeypatch):
    """时效性查询：SHALL 无预搜索伪事件（spec 流式事件真实性）。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="", stock_name=None, status="clarifying")

    captured: dict[str, Any] = {"query": None}

    class _StubAgent:
        async def run(self, user_input: str, force_tool: bool = False):
            captured["query"] = user_input
            return
            yield  # pragma: no cover — 使其成为 async generator

    def _fake_build(**kwargs):
        return _StubAgent()

    async def _fake_stream(agent, user_message, **kwargs):
        # agent.run 为 async generator，消费之
        async for _ in agent.run(user_message):
            pass
        yield f"data: {json.dumps({'type': 'chat_token', 'token': 'ok', 'timestamp': 0})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'timestamp': 0})}\n\n"

    # api.py 在函数内 from agent_factory import ...，须打源模块
    import finance_agent.agent_factory as af

    monkeypatch.setattr(af, "build_agent", _fake_build)
    monkeypatch.setattr(af, "stream_agent_to_sse", _fake_stream)

    published: list[dict] = []

    class _StubRegistry:
        async def publish(self, session_id, data):
            published.append(data)

        async def publish_many(self, session_id, datas):
            published.extend(datas)

    monkeypatch.setattr(api_mod, "registry", _StubRegistry())

    req = AnalyzeRequest(query="今天有什么热门股票", user_id="u1")
    await api_mod._run_react_analysis(sid, req, "aid", 0.0, None, "fake-key", None)

    # 关键断言 1：模型收到的用户消息不含搜索结果注入
    assert captured["query"] is not None
    assert "web_search 的搜索结果" not in captured["query"]
    # 关键断言 2：无预搜索伪事件
    fake_tokens = [
        e
        for e in published
        if e.get("type") == "thinking_token" and "时效性关键词" in str(e.get("token", ""))
    ]
    assert not fake_tokens, f"预搜索伪 thinking_token 仍存在: {fake_tokens[:1]}"
    pre_toolcalls = [
        e for e in published if e.get("type") == "tool_call" and e.get("name") == "web_search"
    ]
    assert not pre_toolcalls, "预搜索伪 tool_call 仍存在"


# ── ② ③ 节点伪 thinking 删除（真实 thinking 转发保留）──


def test_pipeline_stream_no_fake_node_thinking(tmp_path, monkeypatch):
    """管线流：SHALL 无 ▶/✓ 伪 thinking_token；节点真实 thinking 转发保留。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="贵州茅台", status="running")

    class _FakeGraph:
        def stream(self, state, config=None, stream_mode=None):
            yield (
                "custom",
                {"type": "thinking", "token": "真实节点思考", "node": "fundamental_analyst"},
            )
            yield ("updates", {"fundamental_analyst": {"summary": "基本面完成"}})
            yield (
                "updates",
                {"generate_report": {"final_report": "# 报告\n内容", "file_paths": {}}},
            )

    monkeypatch.setattr(api_mod, "graph", _FakeGraph())

    req = AnalyzeRequest(query="600519", api_key="fake")
    raw = list(
        api_mod._run_graph_streaming(
            "600519",
            "贵州茅台",
            req,
            "aid",
            0.0,
            session_id=sid,
            llm_config=None,
        )
    )
    events = _sse_events(raw)
    tokens = [e.get("token", "") for e in events if e.get("type") == "thinking_token"]

    # 关键断言 1：无 ▶/✓ 系统生成 token
    assert not any(t.startswith("\n▶") for t in tokens), "节点开始伪 thinking 仍存在"
    assert not any(t.strip().startswith("✓") for t in tokens), "节点完成伪 thinking 仍存在"
    # 关键断言 2：节点真实 thinking 转发保留
    assert any("真实节点思考" in t for t in tokens)
    # 报告照常产出
    assert any(e.get("type") == "report_ready" for e in events)
