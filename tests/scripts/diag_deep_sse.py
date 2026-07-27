"""Diagnostic SSE client for /api/analyze (deep mode).

Reproduces the '深度模式，输入后无响应' bug by streaming the SSE response
and printing each event with a relative timestamp, so we can see exactly
where (and whether) the stream stalls.

Usage:
    python tests/scripts/diag_deep_sse.py "茅台"
    python tests/scripts/diag_deep_sse.py "300750 估值"   # fast path (stock_code known)
"""

from __future__ import annotations

import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "茅台"
    payload: dict = {"query": query}
    # allow optional stock_code as 2nd arg to test fast path
    if len(sys.argv) > 2:
        payload["stock_code"] = sys.argv[2]

    print(f"[->] POST /api/analyze  query={query!r}  payload={payload}")
    t0 = time.time()

    event_counts: dict[str, int] = {}
    first_event_at: float | None = None
    last_event_at: float | None = None

    try:
        with httpx.stream(
            "POST",
            f"{BASE}/api/analyze",
            json=payload,
            timeout=httpx.Timeout(connect=10, read=120, write=10, pool=10),
        ) as resp:
            print(
                f"[<-] HTTP {resp.status_code}  headers={dict(resp.headers)[:200] if False else {k: v for k, v in resp.headers.items() if k.lower() in ('content-type', 'x-accel-buffering')}}"
            )
            buf = ""
            for raw in resp.iter_text():
                if not raw:
                    continue
                buf += raw
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.rstrip("\r")
                    if not line.startswith("data: "):
                        continue
                    now = time.time() - t0
                    if first_event_at is None:
                        first_event_at = now
                    last_event_at = now
                    data_str = line[len("data: ") :]
                    try:
                        evt = json.loads(data_str)
                        etype = evt.get("type", "?")
                    except json.JSONDecodeError:
                        etype = "<malformed>"
                        evt = {"_raw": data_str[:120]}
                    event_counts[etype] = event_counts.get(etype, 0) + 1
                    # compact preview
                    preview = json.dumps(evt, ensure_ascii=False)
                    if len(preview) > 180:
                        preview = preview[:180] + "…"
                    print(f"[{now:6.2f}s] {etype:<16} {preview}")
    except httpx.ReadTimeout:
        print(f"[!!] ReadTimeout after {time.time() - t0:.2f}s")
    except Exception as e:
        print(f"[!!] Exception after {time.time() - t0:.2f}s: {type(e).__name__}: {e}")

    print("\n===== SUMMARY =====")
    print(f"total elapsed      : {time.time() - t0:.2f}s")
    print(f"first event at     : {first_event_at}")
    print(f"last  event at     : {last_event_at}")
    print(f"event counts       : {event_counts}")
    has_terminal = any(k in event_counts for k in ("done", "error"))
    print(f"terminal event seen: {has_terminal}")


if __name__ == "__main__":
    main()
