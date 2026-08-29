#!/usr/bin/env python
"""每 5 分钟定时观测 Langfuse 实验运行状态（供自动化会话复用）。

口径（与 langfuse 3.205.1 SDK-experiment trace 对齐）:
- 实验 = dataset.run_experiment；每个 item 产生一条 environment=sdk-experiment
  的 trace，metadata.experiment_name 标明所属实验。
- 进度 = 该实验已记录的 item 数 / dataset 总 item 数（当前 16）。
- 运行态判断: 本机存在 evals.run 进程 或 最近一条 item trace 距今 < 5 分钟
  → ONGOING；否则按已收集 item 数是否等于总量给 COMPLETE / INTERRUPTED。

用法:
    uv run python scripts/observe_langfuse_experiments.py [--hours 6]
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATASET_TOTAL = 16  # evals/dataset_items.json 的条目总数
ACTIVE_WINDOW_MIN = 5  # 最近一条 item trace 距今 <= 此值视为仍在产出


def evals_process_alive() -> bool:
    try:
        out = subprocess.run(  # noqa: S603 - 固定参数探测命令,无外部输入
            [
                sys.executable,
                "-c",
                "import psutil,sys;print(any(('evals.run' in ' '.join(p.cmdline()))"
                " or ('run_experiment' in ' '.join(p.cmdline()))"
                " for p in psutil.process_iter()))",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        ).stdout.strip()
        return out == "True"
    except Exception:
        return False


def load_env() -> tuple[str, str, str]:
    load_dotenv(Path(ROOT) / ".env")
    host = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
    pub, sec = os.environ.get("LANGFUSE_PUBLIC_KEY"), os.environ.get("LANGFUSE_SECRET_KEY")
    if not (pub and sec):
        sys.exit("LANGFUSE_PUBLIC_KEY/SECRET_KEY 未配置，无法观测。")
    return host, pub, sec


def fetch_traces(host: str, auth: str, since: str) -> list[dict]:
    q = urllib.parse.urlencode(
        {
            "environment": "sdk-experiment",
            "limit": "100",  # langfuse 3.205.1 上限 100，超出需翻页
            "fromTimestamp": since,  # langfuse API 实际参数名；timestampFrom 会被静默忽略
        }
    )
    req = urllib.request.Request(  # noqa: S310 - 内网 Langfuse,host 来自环境配置
        f"{host}/api/public/traces?{q}", headers={"Authorization": "Basic " + auth}
    )
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - 内网 Langfuse,host 来自环境配置
        return json.loads(r.read()).get("data", [])


def main() -> int:
    host, pub, sec = load_env()
    auth = base64.b64encode(f"{pub}:{sec}".encode()).decode()
    now = datetime.now(UTC)
    since = (now - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    try:
        traces = fetch_traces(host, auth, since)
    except Exception as exc:  # noqa: BLE001
        print(f"[error] 查询 Langfuse 失败: {type(exc).__name__} {exc}")
        return 1

    by_exp: dict[str, list[dict]] = defaultdict(list)
    for t in traces:
        md = t.get("metadata") or {}
        exp = md.get("experiment_name")
        if exp:
            by_exp[exp].append({"item": md.get("dataset_item_id"), "ts": t.get("timestamp")})

    alive = evals_process_alive()
    print(f"观测时间: {now.astimezone().strftime('%Y-%m-%d %H:%M:%S %z')}")
    print(f"evals 进程在跑: {'是' if alive else '否'} | 近 6h 实验 trace 数: {len(traces)}")

    if not by_exp:
        print("-> 近 6 小时无实验运行记录")
        return 0

    for exp in sorted(by_exp):
        rows = sorted(by_exp[exp], key=lambda r: r["ts"])
        items = {r["item"] for r in rows}
        last_dt = datetime.fromisoformat(rows[-1]["ts"].replace("Z", "+00:00"))
        age_min = (now - last_dt).total_seconds() / 60
        if alive or age_min <= ACTIVE_WINDOW_MIN:
            status = "ONGOING"
        elif len(items) >= DATASET_TOTAL:
            status = "COMPLETE"
        else:
            status = "INTERRUPTED"
        print(
            f"- {exp}\n"
            f"    status={status} items={len(items)}/{DATASET_TOTAL} "
            f"last_trace={last_dt.astimezone().strftime('%H:%M:%S')} "
            f"(距今 {age_min:.0f} 分钟)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
