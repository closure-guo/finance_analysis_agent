"""Direct test: does deepseek-chat support tool calling?"""

import json
import os
import sys

sys.path.insert(0, "src")

os.environ["TAVILY_API_KEY"] = os.environ.get("TAVILY_API_KEY", "")

from finance_agent.llm import call_llm_with_tools
from finance_agent.web_search import WEB_SEARCH_TOOL, has_tavily_key

print(f"Tavily key set: {has_tavily_key()}")
print(f"Tool: {json.dumps(WEB_SEARCH_TOOL, ensure_ascii=False, indent=2)}")
print()

resp = call_llm_with_tools(
    "明天天气怎么样",
    system="你是智能助手。对于需要实时信息的问题，请调用 web_search 工具搜索。",
    tools=[WEB_SEARCH_TOOL],
)

msg = resp.choices[0].message
print(f"finish_reason: {resp.choices[0].finish_reason}")
print(f"content: {msg.content}")
print(f"tool_calls: {msg.tool_calls}")

if msg.tool_calls:
    for tc in msg.tool_calls:
        print(f"  tool: {tc.function.name}")
        print(f"  args: {tc.function.arguments}")
