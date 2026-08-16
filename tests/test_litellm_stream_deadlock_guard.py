# tests/test_litellm_stream_deadlock_guard.py
"""litellm 流式 logging 线程死锁防护守护测试。

incident 背景（2026-08-16，docs/incidents/016）：
litellm 1.85.1 流式路径把每个 chunk 的 success logging 提交到全局
ThreadPoolExecutor(100)；worker 内 asyncio.run() 新建 ProactorEventLoop，
Windows + Py3.14 的 _fallback_socketpair 多线程并发竞态 → 线程永久卡在
accept() → 100 worker 全灭 → 退出时 _python_exit join 挂死（跑批 90 分钟
无产出 + 孤儿 127.0.0.1 监听端口均为该根因）。

项目 Langfuse 观测走自研 SDK（start_as_current_observation），未注册任何
litellm callback，禁用 streaming logging 零功能损失。
"""

from __future__ import annotations

import subprocess
import sys

import litellm


def test_llm_module_import_disables_streaming_logging():
    """import finance_agent.llm 后全局开关必须为 True（跑批/管线主路径）。"""
    import finance_agent.llm  # noqa: F401

    assert litellm.disable_streaming_logging is True, (
        "finance_agent.llm 导入后 litellm.disable_streaming_logging 必须为 True，"
        "否则 Windows 上流式 logging 线程会因 socketpair 竞态死锁（incident 016）"
    )


def test_harness_client_import_alone_disables_streaming_logging():
    """仅导入 harness litellm_client（不经过 llm.py）也必须带上开关。

    用子进程隔离 import 缓存，模拟「只走 harness/quick 路径」的独立入口。
    """
    code = (
        "import litellm\n"
        "assert litellm.disable_streaming_logging is not True\n"  # import 前默认 False/None
        "import finance_agent.harness.litellm_client\n"
        "import litellm as lf\n"
        "assert lf.disable_streaming_logging is True, 'harness 独立导入未禁用'\n"
        "print('OK')\n"
    )
    result = subprocess.run(  # noqa: S603 -- sys.executable 固定路径，代码为内联常量
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, f"harness 独立导入防护失败: {result.stderr[-500:]}"
