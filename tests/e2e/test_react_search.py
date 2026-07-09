"""E2E 测试: ReAct 循环 — 模糊查询"光模块龙头企业"。

验证 SSE 事件流：
  thinking_token → tool_call(search_stock) → tool_result → [resolved | tool_call(run_deep_analysis) | 询问用户]

不等待完整 5 层分析（~95s），只验证 ReAct 前半部分。
"""

import json
import sys
import time

import requests

BASE_URL = "http://127.0.0.1:8080"
TIMEOUT = (10, 300)  # (connect, read) — 读取超时 5 分钟，5 层分析需要时间


def test_react_search():
    """测试 ReAct 循环：模糊查询 → 搜索股票 → 决策。"""
    print("=" * 70)
    print("E2E Test: /api/analyze with query='分析一下光模块龙头企业'")
    print("=" * 70)

    resp = requests.post(
        f"{BASE_URL}/api/analyze",
        json={
            "query": "分析一下光模块龙头企业",
            "api_key": "",
        },
        stream=True,
        timeout=TIMEOUT,
    )

    assert resp.status_code == 200, f"HTTP {resp.status_code}"

    events = []
    tool_calls = []
    tool_results = []
    search_result = None
    analysis_started = False
    asked_user = False

    start = time.time()
    for line in resp.iter_lines():
        if not line:
            continue
        line = line.decode()
        if not line.startswith("data: "):
            continue

        event = json.loads(line[6:])
        etype = event.get("type")
        events.append(etype)

        # 打印每个事件
        elapsed = time.time() - start
        if etype == "thinking_token":
            token = event.get("token", "")
            print(f"  [{elapsed:.1f}s] thinking: {token.rstrip()}")
        elif etype == "tool_call":
            tool_name = event.get("name", event.get("tool", ""))
            tool_args = event.get("args", {})
            tool_calls.append((tool_name, tool_args))
            print(f"  [{elapsed:.1f}s] TOOL CALL: {tool_name}({tool_args})")
        elif etype == "tool_result":
            result = event.get("result", {})
            tool_results.append(result)
            if "candidates" in result:
                search_result = result
                candidates = result.get("candidates", [])
                print(
                    f"  [{elapsed:.1f}s] TOOL RESULT: found={result.get('found')}, "
                    f"source={result.get('source')}, "
                    f"{len(candidates)} candidates"
                )
                for c in candidates[:3]:
                    print(f"           - {c.get('stock_name')} ({c.get('stock_code')})")
            else:
                print(f"  [{elapsed:.1f}s] TOOL RESULT: {str(result)[:100]}")
        elif etype == "resolved":
            print(
                f"  [{elapsed:.1f}s] RESOLVED: {event.get('stock_name')} ({event.get('stock_code')})"
            )
            break  # resolved = ReAct 循环完成，不需要等完整 5 层分析
        elif etype == "analysis_start":
            analysis_started = True
            print(
                f"  [{elapsed:.1f}s] ANALYSIS START: {event.get('stock_name')} ({event.get('stock_code')})"
            )
            break  # 不等待完整分析
        elif etype == "error":
            print(f"  [{elapsed:.1f}s] ERROR: {event.get('message')}")
            break
        elif etype == "done":
            print(f"  [{elapsed:.1f}s] DONE")
            break
        else:
            print(f"  [{elapsed:.1f}s] {etype}: {str(event)[:100]}")

        # 如果 LLM 反问用户（thinking_token 后没有 tool_call），标记
        if etype == "thinking_token" and "想分析" in event.get("token", ""):
            asked_user = True

    # ── 验证 ──
    print("\n" + "=" * 70)
    print("VERIFICATION")
    print("=" * 70)

    # 1. 必须有 thinking_token
    assert "thinking_token" in events, f"Missing thinking_token, events: {events}"
    print("✓ thinking_token present")

    # 2. 必须有 tool_call(search_stock)
    search_calls = [c for c in tool_calls if c[0] == "search_stock"]
    assert len(search_calls) > 0, f"No search_stock tool call, tool_calls: {tool_calls}"
    print(f"✓ search_stock called ({len(search_calls)}x)")

    # 3. 必须有 tool_result
    assert len(tool_results) > 0, "No tool results"
    print(f"✓ tool_result received ({len(tool_results)}x)")

    # 4. 搜索结果应该包含候选股票
    if search_result:
        assert search_result.get("found"), f"Search found nothing: {search_result}"
        candidates = search_result.get("candidates", [])
        assert len(candidates) > 0, "No candidates in search result"
        print(f"✓ search found {len(candidates)} candidates")
        # 验证中际旭创在候选中
        codes = [c.get("stock_code") for c in candidates]
        assert "300308" in codes, f"300308 (中际旭创) not in candidates: {codes}"
        print("✓ 中际旭创(300308) in candidates")

    # 5. 要么 resolved（LLM 选了股票），要么 analysis_started，要么反问用户
    resolved = "resolved" in events
    if resolved:
        print("✓ stock resolved (LLM picked a stock for analysis)")
    elif analysis_started:
        print("✓ analysis started (LLM chose a stock)")
    elif asked_user:
        print("✓ LLM asked user to choose (multi-candidate)")
    else:
        print(f"⚠ Neither resolved nor analysis started nor asked user. Events: {events}")

    print(f"\nEvent sequence: {events}")
    print("\n✅ E2E test PASSED")


if __name__ == "__main__":
    try:
        test_react_search()
    except AssertionError as e:
        print(f"\n❌ E2E test FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
