#!/usr/bin/env python
"""数据源门控的 evals 基线跑批（验收用）。

每次触发：
1. 探测 AKShare 数据源（stock_zh_a_spot_em）——不可达则跳过返回（不空转）。
2. 已有 evals 进程在跑则跳过（避免并发双跑）。
3. 均通过 → uv run python -m evals.run baseline-v2-ark-<ts>，落盘系统临时目录
   （走 langfuse run_experiment，实验名带时间戳区分每次 run；langfuse 未配置时
   run.py 显式报错退出——run_experiment 是实验唯一入口，无本地回退）。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_source_reachable() -> bool:
    try:
        import akshare as ak

        df = ak.stock_zh_a_spot_em()
        ok = len(df) > 0
        print(f"[gate] AKShare 数据源可达 rows={len(df)}")
        return ok
    except Exception as exc:  # noqa: BLE001
        print(f"[gate] AKShare 不可达: {type(exc).__name__} {str(exc)[:120]}")
        return False


def evals_running() -> bool:
    out = subprocess.run(  # noqa: S603 - 固定参数探测命令,无外部输入
        [
            sys.executable,
            "-c",
            "import psutil,sys;print(any('evals.run' in ' '.join(p.cmdline()) for p in psutil.process_iter()))",
        ],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return out == "True"


def main() -> int:
    if not data_source_reachable():
        print("[gate] 跳过本轮（数据源不可达）")
        return 0
    if evals_running():
        print("[gate] 跳过本轮（已有 evals 进程在跑）")
        return 0
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    stamp = time.strftime("%Y%m%d-%H%M%S")
    exp_name = f"baseline-v2-ark-{stamp}"
    log_path = os.path.join(tempfile.gettempdir(), "evals-auto.log")
    print(f"[gate] 启动 evals 基线 @ {stamp}（langfuse 实验 {exp_name}）")
    with open(log_path, "a", encoding="utf-8") as log:
        proc = subprocess.run(  # noqa: S603 - 固定模块入口,实验名为本地生成时间戳
            [sys.executable, "-m", "evals.run", exp_name],
            cwd=_ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=False,
            check=False,
        )
    print(f"[gate] evals 结束 exit={proc.returncode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
