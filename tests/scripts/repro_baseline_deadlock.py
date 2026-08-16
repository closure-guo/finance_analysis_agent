"""复现 baseline 跑批死锁：与 evals.run --local 完全同路径跑前 2 行。

上次现场（2026-08-16 12:34 启动的 baseline-v2）：
- 进程启动后 19 分钟无任何 trace（空窗待定位：import / load_items / ？）
- 第 0 行茅台 deep 完整成功（含 judge）
- 第 1 行宁德 deep 卡死在风控辩论 → risk_judge 之间（65+ 分钟 CPU 零增长）

本脚本每阶段打印心跳，配合外部 py-spy dump 取卡点栈。
用法：
    uv run python tests/scripts/repro_baseline_deadlock.py [行索引们...]
默认跑 0 1。
"""

from __future__ import annotations

import os
import sys
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

T0 = time.time()


def beat(msg: str) -> None:
    print(f"[{time.time() - T0:7.1f}s] {msg}", flush=True)
    print(f"[{time.time() - T0:7.1f}s] threads={threading.active_count()}", flush=True)


def main() -> None:
    rows = [int(x) for x in sys.argv[1:]] or [0, 1]

    beat("importing evals.dataset_seed / evals.task ...")
    from evals.dataset_seed import load_items
    from evals.task import run_task

    beat("import done")
    items = load_items()
    beat(f"load_items done: {len(items)} items")

    for i in rows:
        it = items[i]
        q = it["input"].get("query", "?")
        beat(f"row {i} [{it['input'].get('mode')}] {q[:36]} START")
        try:
            out = run_task(item=it, expected_output=it.get("expected_output"))
            beat(
                f"row {i} DONE mode={out.get('mode')} report_len="
                f"{len(out.get('report') or '')} skipped={out.get('skipped')}"
            )
        except Exception as e:  # noqa: BLE001
            beat(f"row {i} FAILED {type(e).__name__}: {str(e)[:200]}")

    beat("ALL DONE — 若进程未退出即为退出阶段死锁（上次 incident 已知问题）")


if __name__ == "__main__":
    main()
