"""验证 _ChatCollector 对预搜索事件的 agentTimeline 构建。

Bug 根因：_run_react_analysis 中时效性查询的预搜索逻辑，
search_start/search_result 事件只 registry.publish（推送前端实时），
没有 collector.feed（不进入持久化的 agentTimeline）。
导致 chat_history.agentTimeline 缺少 search item，刷新后搜索横幅消失。

修复标准：collector.feed 处理 search_start/search_result 后，
agent_timeline 应包含 search item。
"""

from finance_agent.api import _ChatCollector
from finance_agent.timeline_builder import apply_chat_event


def test_collector_feed_search_events_builds_search_item():
    """collector.feed 处理 search_start + search_result 后 agent_timeline 应含 search item。

    复现 Bug：预搜索流程的 search_start/search_result 没 feed，
    agent_timeline 只有 thinking，缺少 search item。
    """
    collector = _ChatCollector()

    # 模拟预搜索流程的事件序列（api.py:1219-1269）
    events = [
        {"type": "thinking_token", "token": "用户询问包含时效性关键词，我先搜索最新市场信息。\n"},
        {"type": "tool_call", "name": "web_search", "args": {"query": "热门股票 A股"}},
        # 关键：search_start 必须 feed 才能生成 search item
        {"type": "search_start", "query": "热门股票 A股"},
        {"type": "tool_result", "name": "web_search", "result": "搜索结果摘要..."},
        # 关键：search_result 必须 feed 才能更新 search item 为 done
        {
            "type": "search_result",
            "query": "热门股票 A股",
            "results": [{"title": "热门股票", "url": "http://x", "content": "..."}],
            "count": 1,
        },
    ]

    for ev in events:
        collector.feed(ev)

    # 关键断言：agent_timeline 应包含 search item
    search_items = [item for item in collector.agent_timeline if item.get("type") == "search"]
    assert len(search_items) >= 1, (
        f"agent_timeline 缺少 search item。实际 agent_timeline: {collector.agent_timeline}"
    )

    # search item 应为 done 状态（search_result 已回填）
    assert search_items[-1].get("status") == "done"
    assert search_items[-1].get("results"), "search item 应有 results"


def test_apply_chat_event_search_start_creates_searching_item():
    """apply_chat_event 处理 search_start 应生成 searching 状态的 search item。"""
    timeline = []
    timeline = apply_chat_event(timeline, {"type": "search_start", "query": "测试查询"})

    search_items = [item for item in timeline if item.get("type") == "search"]
    assert len(search_items) == 1
    assert search_items[0].get("status") == "searching"
    assert search_items[0].get("query") == "测试查询"
