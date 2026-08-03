"""search_stock 工具事件循环阻塞测试。

Bug 根因：search_stock async 工具直接调用同步 search_stock_tool（含 AKShare 重试），
未用 asyncio.to_thread 包装，阻塞事件循环。表现为：
- 工具调用执行中切换会话，所有 API 请求被挂起（事件循环阻塞）
- 刷新页面后 /api/sessions 超时，前端显示历史会话清空（实际数据未丢）
- UI 卡顿、无法切回原会话

修复标准：search_stock 内部调用 search_stock_tool 必须通过 asyncio.to_thread 包装，
让同步阻塞操作在线程池执行，不阻塞事件循环。
"""

import asyncio
import contextlib
import time
from unittest.mock import patch

import pytest

from finance_agent.agent_factory import _make_search_stock


class TestSearchStockEventLoopBlocking:
    """验证 search_stock 不阻塞事件循环。"""

    @pytest.mark.asyncio
    async def test_search_stock_does_not_block_event_loop(self):
        """search_stock 执行期间，事件循环必须保持响应。

        复现 Bug：search_stock 同步调用 search_stock_tool 时，
        事件循环被阻塞，并发的 asyncio.sleep 无法按时完成。
        """

        # 模拟 search_stock_tool 同步阻塞 1 秒（AKShare 重试场景）
        def slow_sync_call(query, api_key):
            time.sleep(1)
            return {
                "candidates": [{"code": "600519", "name": "贵州茅台", "market": "SH"}],
                "found": True,
                "source": "akshare_exact",
                "confidence": 1.0,
            }

        with patch("finance_agent.react_agent.search_stock_tool", side_effect=slow_sync_call):
            search_stock = _make_search_stock(api_key="test-key")

            # 计数器：事件循环每 50ms 唤醒一次计数
            # 1 秒阻塞期间，若事件循环未阻塞应计数约 20 次；若被阻塞则计数 0 次
            wakeup_count = 0

            async def periodic_wakeup():
                nonlocal wakeup_count
                while True:
                    await asyncio.sleep(0.05)
                    wakeup_count += 1

            wakeup_task = asyncio.create_task(periodic_wakeup())

            # 启动 search_stock（async），等待其完成
            start_time = time.time()
            await search_stock(query="茅台")
            elapsed = time.time() - start_time

            # 让 wakeup 再跑一会儿，确保计数准确
            await asyncio.sleep(0.2)
            wakeup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await wakeup_task

        # search_stock 至少耗时 1 秒（同步 sleep 1 秒）
        assert elapsed >= 1.0, f"search_stock 应至少耗时 1 秒，实际 {elapsed:.2f}s"

        # 关键断言：1 秒执行期间 + 0.2 秒收尾，事件循环应能唤醒多次
        # Bug 复现：事件循环被阻塞 1 秒，wakeup 全部堆到阻塞结束后，
        # 1.2 秒窗口内仅能唤醒约 4 次（0.2 秒 / 0.05 秒）
        # 修复后：1.2 秒窗口内应能唤醒约 24 次
        # 阈值取 10：明确区分阻塞（<4）与未阻塞（>20）
        assert wakeup_count >= 10, (
            f"事件循环被阻塞：1.2 秒窗口内仅唤醒 {wakeup_count} 次（应 >= 10）。"
            f"search_stock 同步调用阻塞了事件循环。"
        )
