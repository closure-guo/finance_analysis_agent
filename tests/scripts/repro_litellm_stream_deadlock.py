"""复现 litellm 流式 logging 线程泄漏/死锁（Windows + Python 3.14 + litellm 1.85.1）。

背景（incident: baseline-v2 跑批 90 分钟运行中死锁）：
- litellm 流式路径每个 chunk 向全局 ThreadPoolExecutor(100) 提交
  run_success_logging_and_cache_storage
- 该函数在 logging_loop 为 None 时 asyncio.run() 新建 event loop，
  Windows Proactor 的 self-pipe 通过 bind 127.0.0.1 随机端口模拟 socketpair
- 线程若卡在无超时的 future.result()，泄漏一对监听端口

验证指标（每轮打印）：
- threading.active_count()：活跃线程数，持续增长 = 线程泄漏
- 本进程 PID 名下 127.0.0.1 LISTENING 端口数：持续增长 = socketpair 泄漏

用法：
    uv run python tests/scripts/repro_litellm_stream_deadlock.py [轮数] [每轮并发]
默认 10 轮 × 并发 3。若线程/端口数随轮次单调上涨 → 复现泄漏；
若进程最终不退出或调用挂死 → 复现死锁（用 py-spy dump 取证）。
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

from dotenv import load_dotenv

load_dotenv()

import litellm  # noqa: E402
from litellm import completion  # noqa: E402

litellm.suppress_debug_info = True


def _listen_port_count(pid: int) -> int:
    out = subprocess.run(
        ["netstat", "-ano", "-p", "TCP"],  # noqa: S607 -- 一次性诊断脚本，netstat 为系统命令
        capture_output=True,
    ).stdout.decode("gbk", errors="ignore")
    return sum(
        1
        for line in out.splitlines()
        if "LISTENING" in line and "127.0.0.1:" in line and line.rstrip().endswith(str(pid))
    )


def _one_streaming_call(seq: int) -> int:
    resp = completion(
        model=os.environ["LLM_MODEL"],
        api_key=os.environ["LLM_API_KEY"],
        base_url=os.environ["LLM_BASE_URL"],
        messages=[{"role": "user", "content": f"从 1 数到 15，只输出数字（第 {seq} 批）"}],
        stream=True,
        max_tokens=150,
        timeout=60,
    )
    chunks = 0
    for _ in resp:
        chunks += 1
    return chunks


def main() -> None:
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    conc = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    pid = os.getpid()
    print(f"pid={pid} rounds={rounds} concurrency={conc}", flush=True)

    for i in range(rounds):
        threads = []
        lock = threading.Lock()

        def worker(seq: int, lock: threading.Lock = lock) -> None:
            t0 = time.time()
            try:
                n = _one_streaming_call(seq)
                ok = 1
            except Exception as e:  # noqa: BLE001
                print(f"  call {seq} FAILED: {type(e).__name__}: {str(e)[:80]}", flush=True)
                n, ok = 0, 0
            with lock:
                print(f"  call {seq}: chunks={n} {time.time() - t0:.1f}s", flush=True)

        for j in range(conc):
            t = threading.Thread(target=worker, args=(i * conc + j,))
            threads.append(t)
            t.start()
        for t in threads:
            t.join(timeout=90)

        stuck = sum(1 for t in threads if t.is_alive())
        print(
            f"round {i:2}: threads={threading.active_count()} "
            f"listen_ports={_listen_port_count(pid)} stuck_threads={stuck}",
            flush=True,
        )
        if stuck:
            print("!! 有线程 90s 未完成 —— 死锁复现，立即停止", flush=True)
            break

    print("done", flush=True)


if __name__ == "__main__":
    main()
