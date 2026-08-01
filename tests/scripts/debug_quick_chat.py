"""调试脚本：在 Docker 内运行 stream_agent_to_sse 完整流程，打印每个事件及到达时间。"""

import asyncio
import logging
import os
import sys
import time

# 彻底禁用 Langfuse
for k in list(os.environ.keys()):
    if "LANGFUSE" in k.upper():
        del os.environ[k]

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from finance_agent.agent_factory import build_agent, stream_agent_to_sse  # noqa: E402


async def main() -> None:
    agent = build_agent(mode="quick")
    startTs = time.monotonic()
    count = 0
    try:

        async def gen() -> None:
            nonlocal count
            async for s in stream_agent_to_sse(agent, "沈阳天气"):
                count += 1
                elapsed = time.monotonic() - startTs
                firstLine = s.split("\n", 1)[0]
                if firstLine.startswith("data:"):
                    preview = firstLine[5:].strip()[:150]
                else:
                    preview = firstLine[:60]
                print(f"[{elapsed:6.1f}s] #{count}: {preview}", flush=True)
                if count > 500:
                    break

        await asyncio.wait_for(gen(), timeout=120)
        print(f"DONE, {count} events")
    except TimeoutError:
        print(f"TIMEOUT after 120s, {count} events")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}, {count} events")


asyncio.run(main())
sys.exit(0)
