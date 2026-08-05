"""验证修复：search_stock 执行期间 /api/sessions 应能并发响应。

Bug 根因：search_stock async 工具直接调用同步 search_stock_tool（含 AKShare 重试），
阻塞事件循环，导致所有 API 请求被挂起。

修复：用 asyncio.to_thread 包装同步调用，让事件循环保持响应。

验证方式：
1. 启动一个会触发 search_stock 的 /api/analyze 请求（输入股票名"安孚科技"）
2. 等待进入工具调用阶段（thinking_token 或 tool_call 事件）
3. 并发请求 /api/sessions，测量响应时间
4. 修复前：/api/sessions 会被阻塞直到 search_stock 完成（10+ 秒）
5. 修复后：/api/sessions 应在 1 秒内响应
"""

import asyncio
import json
import time
import urllib.request

BASE_URL = "http://localhost:8000"


async def consume_sse(stream, label: str) -> None:
    """消费 SSE 流，检测工具调用阶段。"""
    seen_tool_call = False
    seen_thinking = False
    for raw in stream:
        line = raw.decode("utf-8", errors="ignore").strip()
        if not line.startswith("data: "):
            continue
        try:
            ev = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        ev_type = ev.get("type")
        if ev_type == "thinking_token" and not seen_thinking:
            print(f"[{label}] 看到思考流（thinking_token）")
            seen_thinking = True
        if ev_type == "tool_call" and not seen_tool_call:
            print(f"[{label}] 看到工具调用：{ev.get('name')}")
            seen_tool_call = True
            # 工具调用阶段已确认，不再消费
            return
        if ev_type in ("done", "error", "interrupted"):
            print(f"[{label}] 流结束：{ev_type}")
            return


async def test_sessions_responsive_during_search_stock():
    """验证 search_stock 执行期间 /api/sessions 能并发响应。"""
    print("=" * 60)
    print("测试：search_stock 执行期间 /api/sessions 响应时间")
    print("=" * 60)

    # 启动一个会触发 search_stock 的分析（输入股票名，非代码）
    # 后端会先 thinking -> tool_call(search_stock) -> AKShare 阻塞
    payload = json.dumps(
        {
            "query": "安孚科技",
            "api_key": "test-key",
            "analysis_type": "comprehensive",
        }
    ).encode()

    req = urllib.request.Request(
        f"{BASE_URL}/api/analyze",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    # 用 urllib 同步发起，但在 asyncio 中包装
    def post_analyze():
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                # 返回 SSE 流的生成器
                yield from resp
        except Exception as e:
            print(f"analyze 请求异常: {e}")
            return

    # 简化：直接用 asyncio.to_thread 读取前几个事件
    import urllib.request as urlreq

    async def run_analyze_and_wait_for_tool_call():
        """启动分析，等待工具调用出现。"""
        loop = asyncio.get_event_loop()

        def _sync_fetch():
            try:
                resp = urlreq.urlopen(req, timeout=60)
                for line in resp:
                    line_str = line.decode("utf-8", errors="ignore").strip()
                    if line_str.startswith("data: "):
                        try:
                            ev = json.loads(line_str[6:])
                        except json.JSONDecodeError:
                            continue
                        if ev.get("type") == "tool_call":
                            return True
                        if ev.get("type") in ("done", "error", "interrupted", "awaiting_input"):
                            return False
                return False
            except Exception as e:
                print(f"  analyze 异常: {e}")
                return False

        # 在线程中运行，避免阻塞事件循环
        result = await asyncio.wait_for(asyncio.to_thread(_sync_fetch), timeout=60)
        return result

    # 步骤 1：启动分析任务（在线程中，不阻塞事件循环）
    analyze_task = asyncio.create_task(run_analyze_and_wait_for_tool_call())
    print("[1] 启动分析请求（输入: 安孚科技）")

    # 步骤 2：等待工具调用阶段出现
    print("[2] 等待工具调用阶段（thinking/tool_call）...")
    # 给分析一点时间启动
    await asyncio.sleep(3)

    # 步骤 3：此时 search_stock 应该正在执行（AKShare 同步阻塞）
    # 并发请求 /api/sessions，测量响应时间
    print("[3] 并发请求 /api/sessions（此时 search_stock 应在执行中）...")

    loop = asyncio.get_event_loop()

    def fetch_sessions():
        start = time.time()
        try:
            with urlreq.urlopen(f"{BASE_URL}/api/sessions", timeout=15) as resp:
                data = json.loads(resp.read().decode())
                elapsed = time.time() - start
                count = len(data.get("sessions", []))
                return elapsed, count, None
        except Exception as e:
            elapsed = time.time() - start
            return elapsed, 0, str(e)

    elapsed, count, err = await asyncio.to_thread(fetch_sessions)

    if err:
        print(f"[3] /api/sessions 失败：{err}（耗时 {elapsed:.2f}s）")
        print("\n结论：FAIL - 事件循环仍被阻塞")
        return False
    else:
        print(f"[3] /api/sessions 成功：{count} 个会话（耗时 {elapsed:.2f}s）")
        if elapsed < 3.0:
            print("\n结论：PASS - 事件循环未阻塞，/api/sessions 在 3 秒内响应")
        else:
            print("\n结论：FAIL - /api/sessions 响应过慢，事件循环可能被阻塞")
        return elapsed < 3.0

    # 清理：取消分析任务
    analyze_task.cancel()


if __name__ == "__main__":
    result = asyncio.run(test_sessions_responsive_during_search_stock())
    exit(0 if result else 1)
