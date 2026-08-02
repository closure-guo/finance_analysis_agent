"""手动验证 trace-observability 的 Langfuse trace 结构。

启动服务后运行此脚本，触发一次含工具调用 + 搜索的 chat，
然后拉取 Langfuse trace，断言 trace 含 tool:{name} 与 search_api_call span。

用法:
    uv run python tests/scripts/verify_trace_observability.py

前置条件:
    - 后端服务运行中（http://localhost:8000）
    - Langfuse 运行中（http://localhost:3000）
    - TAVILY_API_KEY 已配置
"""

import json

import httpx

BACKEND_URL = "http://localhost:8000"
LANGFUSE_URL = "http://localhost:3000"


def trigger_chat_with_search():
    """触发一次含时效性关键词的 chat，诱导工具调用 + 搜索。"""
    print("[1/3] 触发 chat 请求（含时效关键词）...")
    sessionId = None
    # /api/chat 返回 SSE 流，session_id 通过 session_created 事件下发
    with (
        httpx.Client(timeout=120) as client,
        client.stream(
            "POST",
            f"{BACKEND_URL}/api/chat",
            json={"message": "今天 A 股市场有什么最新消息？", "session_id": None},
        ) as response,
    ):
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[len("data: ") :])
            except json.JSONDecodeError:
                continue
            if data.get("type") == "session_created" and data.get("session_id"):
                sessionId = data["session_id"]
                print(f"    会话 ID: {sessionId}")
        # 流读完即表示后端处理完成，无需额外 sleep
    if sessionId is None:
        print("    ⚠️ 未收到 session_created 事件")
    return sessionId


def fetch_langfuse_trace(sessionId):
    """从 Langfuse 拉取该会话的 trace。"""
    print(f"[2/3] 拉取 Langfuse trace（session={sessionId}）...")
    with httpx.Client(timeout=30) as client:
        response = client.get(
            f"{LANGFUSE_URL}/api/public/traces",
            params={"session_id": sessionId},
        )
        traces = response.json().get("data", [])
        if not traces:
            print("    ⚠️ 未找到 trace，请确认 Langfuse 已记录")
            return None
        return traces[0]


def assert_span_structure(trace):
    """断言 trace 含 tool:{name} 与 search_api_call span。"""
    print("[3/3] 断言 trace span 结构...")
    observations = trace.get("observations", [])
    spanNames = [obs.get("name") for obs in observations]

    hasToolSpan = any(name and name.startswith("tool:") for name in spanNames)
    hasSearchSpan = "search_api_call" in spanNames

    print(f"    span 列表: {spanNames}")
    print(f"    含 tool:* span: {'✅' if hasToolSpan else '❌'}")
    print(f"    含 search_api_call span: {'✅' if hasSearchSpan else '❌'}")

    if hasToolSpan and hasSearchSpan:
        print("\n✅ 验证通过：trace 含工具调用 span 与网络搜索 span，分层可观测")
    else:
        print("\n❌ 验证失败：trace 缺少必要的 span")
        raise SystemExit(1)


def main():
    sessionId = trigger_chat_with_search()
    trace = fetch_langfuse_trace(sessionId)
    if trace:
        assert_span_structure(trace)
    else:
        print("⚠️ 无法拉取 trace，请人工登录 Langfuse UI 查看")


if __name__ == "__main__":
    main()
