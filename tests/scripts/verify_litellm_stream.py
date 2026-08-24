"""测试 litellm streaming 是否会卡住。"""

import asyncio
import os

import litellm


async def test():
    key = os.environ.get("LLM_API_KEY", "")
    print("Starting litellm.acompletion stream...")
    resp = await litellm.acompletion(
        model="deepseek/deepseek-chat",
        messages=[{"role": "user", "content": "说3个字"}],
        api_key=key,
        stream=True,
        timeout=15,
    )
    print(f"Response type: {type(resp).__name__}")
    count = 0
    try:
        async for chunk in resp:
            count += 1
            text = getattr(chunk.choices[0].delta, "content", "") or ""
            if count <= 5:
                print(f"  Chunk {count}: '{text}'")
        print(f"Stream completed: {count} chunks")
    except Exception as e:
        print(f"Stream error after {count} chunks: {type(e).__name__}: {e}")


asyncio.run(asyncio.wait_for(test(), timeout=30))
