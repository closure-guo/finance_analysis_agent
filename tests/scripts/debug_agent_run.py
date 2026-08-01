"""调试：直接消费 agent.run() 原始事件流，定位卡点。"""

import asyncio
import os
import time

for k in list(os.environ.keys()):
    if "LANGFUSE" in k.upper():
        del os.environ[k]

import logging

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from finance_agent.agent_factory import build_agent  # noqa: E402


async def main() -> None:
    agent = build_agent(mode="quick")
    startTs = time.monotonic()
    count = 0
    try:

        async def gen() -> None:
            nonlocal count
            async for event in agent.run("沈阳天气"):
                count += 1
                elapsed = time.monotonic() - startTs
                content = (event.content or "")[:80].replace("\n", " ")
                toolName = ""
                if event.tool_call:
                    toolName = f" tool={event.tool_call.name}"
                if event.tool_result:
                    toolName = f" result={event.tool_result.name} err={event.tool_result.is_error}"
                print(
                    f"[{elapsed:6.1f}s] #{count} {event.event_type}{toolName} | {content}",
                    flush=True,
                )
                if count > 300:
                    break

        await asyncio.wait_for(gen(), timeout=120)
        print(f"DONE, {count} events", flush=True)
    except TimeoutError:
        print(f"TIMEOUT after 120s, {count} events", flush=True)
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}, {count} events", flush=True)


asyncio.run(main())
