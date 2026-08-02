"""调试：单独测试 _web_search 与 hooks.emit，定位事件循环冻结点。"""

import asyncio
import os
import time

for k in list(os.environ.keys()):
    if "LANGFUSE" in k.upper():
        del os.environ[k]

import logging

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


async def testWebSearch() -> None:
    from finance_agent.agent_factory import _web_search

    startTs = time.monotonic()
    print(f"[{0:5.1f}s] calling _web_search...", flush=True)
    try:
        result = await _web_search("沈阳天气 今天 实时")
        elapsed = time.monotonic() - startTs
        print(f"[{elapsed:5.1f}s] _web_search OK, {len(result)} chars", flush=True)
        print(result[:300], flush=True)
    except Exception as e:
        elapsed = time.monotonic() - startTs
        print(f"[{elapsed:5.1f}s] _web_search FAIL: {type(e).__name__}: {e}", flush=True)


async def testAgentToolExecute() -> None:
    """通过 Agent 的 ToolManager 执行 web_search，模拟真实 ReAct 路径。"""
    from finance_agent.agent_factory import build_agent

    agent = build_agent(mode="quick")
    startTs = time.monotonic()
    print(f"[{0:5.1f}s] tools.execute web_search via agent...", flush=True)
    try:
        result = await asyncio.wait_for(
            agent.tools.execute("tc-1", "web_search", {"query": "沈阳天气 今天 实时"}),
            timeout=60.0,
        )
        elapsed = time.monotonic() - startTs
        print(
            f"[{elapsed:5.1f}s] execute done, is_error={result.is_error}, "
            f"duration_ms={result.duration_ms}",
            flush=True,
        )
        print(result.output[:300], flush=True)
    except Exception as e:
        elapsed = time.monotonic() - startTs
        print(f"[{elapsed:5.1f}s] execute FAIL: {type(e).__name__}: {e}", flush=True)


async def main() -> None:
    await testWebSearch()
    print("---", flush=True)
    await testAgentToolExecute()


asyncio.run(main())
