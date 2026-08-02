"""SSE 心跳保护测试。

对应 change: harden-react-path-resilience Task 4.1。
验证 ReAct 路径 SSE 空闲超过 heartbeat_interval 后 SHALL 收到心跳注释。
"""

from __future__ import annotations

import asyncio

import pytest

from finance_agent.harness import StreamEvent


@pytest.mark.asyncio
async def test_sse_heartbeat_on_idle():
    """SSE 空闲超过 heartbeat_interval 后 SHALL 收到心跳注释。"""
    from finance_agent.agent_factory import stream_agent_to_sse

    # Mock agent：run() 先 sleep 再 yield 事件
    class MockAgent:
        async def run(self, user_input, force_tool=False):
            await asyncio.sleep(0.3)  # 模拟空闲
            yield StreamEvent.answer("test response")

    agent = MockAgent()
    results: list[str] = []
    async for sse_str in stream_agent_to_sse(agent, "test", heartbeat_interval=0.1):
        results.append(sse_str)

    # 应该至少有一个心跳注释
    heartbeats = [s for s in results if "heartbeat" in s]
    assert len(heartbeats) >= 1


@pytest.mark.asyncio
async def test_sse_heartbeat_does_not_interfere_events():
    """心跳 SHALL NOT 干扰正常事件流。"""
    from finance_agent.agent_factory import stream_agent_to_sse

    class MockAgent:
        async def run(self, user_input, force_tool=False):
            yield StreamEvent.answer("hello")
            yield StreamEvent.answer("world")

    agent = MockAgent()
    results: list[str] = []
    async for sse_str in stream_agent_to_sse(agent, "test", heartbeat_interval=15.0):
        results.append(sse_str)

    # 正常事件应全部到达
    chat_tokens = [s for s in results if "chat_token" in s]
    assert len(chat_tokens) == 2
    # 无心跳（事件间隔远小于 15s）
    heartbeats = [s for s in results if "heartbeat" in s]
    assert len(heartbeats) == 0
    # 应有 chat_done
    done_events = [s for s in results if "chat_done" in s]
    assert len(done_events) == 1
