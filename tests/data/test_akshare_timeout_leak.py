"""复现测试：_call_ak 超时机制失效导致线程泄漏打满 executor 池。

根因：_call_ak 用 `with ThreadPoolExecutor(max_workers=1) as pool`，
future.result(timeout) 超时后，with 退出调用 pool.shutdown(wait=True)，
会无限等待那个仍在运行的 AKShare 线程结束——超时形同虚设，线程被死死占住。
PREP 阶段约 12 次 AKShare 调用 * 3 次重试，若 AKShare 限频/无响应，
泄漏线程打满默认 executor 池，事件循环上后续 to_thread/run_in_executor
（含 /api/sessions、/api/health）排队超时，前端表现为「会话清空」。

修复标准：AKShare 调用超时后 _call_ak 应及时返回（不被 shutdown 阻塞）。
"""

import time

from finance_agent.data import akshare_client
from finance_agent.data.akshare_client import _call_ak

# 慢速线程持续时间：足够长以证明「_call_ak 远早于此返回」，
# 但有限（非永久），保证测试进程能干净退出（non-daemon 线程最终结束）。
_SLOW_DURATION = 20


def _slow_call() -> None:
    """模拟 AKShare 慢响应：sleep _SLOW_DURATION 秒后才返回。"""
    time.sleep(_SLOW_DURATION)


def test_call_ak_timeout_does_not_block_on_shutdown(monkeypatch):
    """超时后 _call_ak 应在 ~超时时间内返回，不被 pool.shutdown(wait=True) 卡住。"""
    monkeypatch.setattr(akshare_client, "_AK_TIMEOUT", 1)
    monkeypatch.setattr(akshare_client, "_AK_MAX_RETRIES", 1)
    monkeypatch.setattr(akshare_client, "_AK_RETRY_DELAY", 0)

    start = time.monotonic()
    result = _call_ak(_slow_call)
    elapsed = time.monotonic() - start

    assert result is None  # 超时/重试耗尽返回 None
    # 修复前：shutdown(wait=True) 等待 _SLOW_DURATION(20s) 才返回，elapsed ~20s
    # 修复后：超时(1s)即返回，elapsed 应在超时附近（<5s 留余量）
    assert elapsed < 5, f"_call_ak 超时被 shutdown 阻塞，耗时 {elapsed:.1f}s"


def test_call_ak_timeout_unblocks_subsequent_calls(monkeypatch):
    """前一次超时调用不阻塞后续调用（executor 引用被释放，不再串行等待）。"""
    monkeypatch.setattr(akshare_client, "_AK_TIMEOUT", 1)
    monkeypatch.setattr(akshare_client, "_AK_MAX_RETRIES", 1)
    monkeypatch.setattr(akshare_client, "_AK_RETRY_DELAY", 0)

    start = time.monotonic()
    # 连续 3 次超时调用。修复前每次 shutdown 串行等待 20s -> 总 ~60s；
    # 修复后每次 1s -> 总 ~3s。
    for _ in range(3):
        assert _call_ak(_slow_call) is None
    elapsed = time.monotonic() - start

    assert elapsed < 10, f"连续超时调用被串行阻塞，总耗时 {elapsed:.1f}s"
