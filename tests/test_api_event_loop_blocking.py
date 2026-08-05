"""session_store 同步调用事件循环阻塞测试。

Bug 根因：FastAPI 路由处理函数与后台任务协程内直接同步调用
session_store 的 sqlite3 函数（list_sessions / get_session 等），
阻塞事件循环线程，与 PipelineRunner 后台线程的高频写竞争，
导致 GET /api/sessions 等请求间歇性挂起，前端表现为刷新后历史会话清空。

修复标准：async 函数内对 session_store 的同步直调必须通过
asyncio.to_thread 包装，让同步阻塞操作在线程池执行，不阻塞事件循环。
"""

import asyncio
import contextlib
import time
from unittest.mock import patch

import pytest

import finance_agent.api as api_mod


class TestSessionStoreEventLoopBlocking:
    """验证 session_store 相关 API 不阻塞事件循环。"""

    @pytest.mark.asyncio
    async def test_get_sessions_does_not_block_event_loop(self):
        """GET /api/sessions 执行期间，事件循环必须保持响应。

        复现 Bug：list_sessions 同步执行时事件循环被阻塞，
        并发的 asyncio.sleep 无法按时完成。
        """

        # 模拟 list_sessions 同步阻塞 0.5 秒（SQLite 慢查询场景）
        def slow_list_sessions():
            time.sleep(0.5)
            return []

        with patch.object(api_mod, "list_sessions", side_effect=slow_list_sessions):
            # 计数器：事件循环每 50ms 唤醒一次计数
            # 0.5 秒阻塞期间，若事件循环未阻塞应计数约 10 次；若被阻塞则计数 0 次
            wakeup_count = 0

            async def periodic_wakeup():
                nonlocal wakeup_count
                while True:
                    await asyncio.sleep(0.05)
                    wakeup_count += 1

            wakeup_task = asyncio.create_task(periodic_wakeup())

            start_time = time.time()
            # 直接调用路由处理函数（async def get_sessions）
            result = await api_mod.get_sessions()
            elapsed = time.time() - start_time

            # 让 wakeup 再跑一会儿，确保计数准确
            await asyncio.sleep(0.1)
            wakeup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await wakeup_task

        assert result == {"sessions": []}
        assert elapsed >= 0.5, f"get_sessions 应至少耗时 0.5 秒，实际 {elapsed:.2f}s"

        # 关键断言：0.6 秒窗口内应能唤醒多次
        # Bug 复现：事件循环被阻塞 0.5 秒，wakeup 全部堆到阻塞结束后，
        # 0.6 秒窗口内仅能唤醒约 2 次（0.1 秒 / 0.05 秒）
        # 修复后：0.6 秒窗口内应能唤醒约 12 次
        # 阈值取 5：明确区分阻塞（<3）与未阻塞（>10）
        assert wakeup_count >= 5, (
            f"事件循环被阻塞：0.6 秒窗口内仅唤醒 {wakeup_count} 次（应 >= 5）。"
            f"list_sessions 同步调用阻塞了事件循环。"
        )

    @pytest.mark.asyncio
    async def test_get_session_detail_does_not_block_event_loop(self):
        """GET /api/sessions/{id} 执行期间，事件循环必须保持响应。"""

        def slow_get_session(session_id):
            time.sleep(0.5)
            return {"id": session_id, "status": "completed"}

        with patch.object(api_mod, "get_session", side_effect=slow_get_session):
            wakeup_count = 0

            async def periodic_wakeup():
                nonlocal wakeup_count
                while True:
                    await asyncio.sleep(0.05)
                    wakeup_count += 1

            wakeup_task = asyncio.create_task(periodic_wakeup())

            start_time = time.time()
            result = await api_mod.get_session_detail("test-sid")
            elapsed = time.time() - start_time

            await asyncio.sleep(0.1)
            wakeup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await wakeup_task

        assert result["id"] == "test-sid"
        assert elapsed >= 0.5

        assert wakeup_count >= 5, (
            f"事件循环被阻塞：0.6 秒窗口内仅唤醒 {wakeup_count} 次（应 >= 5）。"
            f"get_session 同步调用阻塞了事件循环。"
        )

    @pytest.mark.asyncio
    async def test_rename_session_does_not_block_event_loop(self):
        """PATCH /api/sessions/{id} 执行期间，事件循环必须保持响应。"""

        def slow_rename_session(session_id, display_name):
            time.sleep(0.5)
            return True

        with patch.object(api_mod, "rename_session", side_effect=slow_rename_session):
            wakeup_count = 0

            async def periodic_wakeup():
                nonlocal wakeup_count
                while True:
                    await asyncio.sleep(0.05)
                    wakeup_count += 1

            wakeup_task = asyncio.create_task(periodic_wakeup())

            start_time = time.time()
            result = await api_mod.rename_session_api(
                "test-sid", api_mod.RenameRequest(display_name="新名称")
            )
            elapsed = time.time() - start_time

            await asyncio.sleep(0.1)
            wakeup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await wakeup_task

        assert result == {"ok": True}
        assert elapsed >= 0.5

        assert wakeup_count >= 5, (
            f"事件循环被阻塞：0.6 秒窗口内仅唤醒 {wakeup_count} 次（应 >= 5）。"
            f"rename_session 同步调用阻塞了事件循环。"
        )

    @pytest.mark.asyncio
    async def test_delete_session_does_not_block_event_loop(self):
        """DELETE /api/sessions/{id} 执行期间，事件循环必须保持响应。"""

        def slow_delete_session(session_id):
            time.sleep(0.5)
            return True

        with patch.object(api_mod, "delete_session", side_effect=slow_delete_session):
            wakeup_count = 0

            async def periodic_wakeup():
                nonlocal wakeup_count
                while True:
                    await asyncio.sleep(0.05)
                    wakeup_count += 1

            wakeup_task = asyncio.create_task(periodic_wakeup())

            start_time = time.time()
            result = await api_mod.delete_session_api("test-sid")
            elapsed = time.time() - start_time

            await asyncio.sleep(0.1)
            wakeup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await wakeup_task

        assert result == {"ok": True}
        assert elapsed >= 0.5

        assert wakeup_count >= 5, (
            f"事件循环被阻塞：0.6 秒窗口内仅唤醒 {wakeup_count} 次（应 >= 5）。"
            f"delete_session 同步调用阻塞了事件循环。"
        )
