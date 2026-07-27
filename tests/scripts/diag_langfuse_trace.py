"""Query Langfuse for traces/observations of a session to localize the failure."""

from __future__ import annotations

import base64
import os
import sys

import httpx

BASE = "http://localhost:3000"


def main() -> None:
    pk = os.environ.get("LF_PK")
    sk = os.environ.get("LF_SK")
    if not pk or not sk:
        print("set LF_PK and LF_SK env vars")
        sys.exit(1)
    token = base64.b64encode(f"{pk}:{sk}".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}

    # list recent traces
    r = httpx.get(
        f"{BASE}/api/public/traces?limit=12&orderBy=timestamp.desc", headers=headers, timeout=30
    )
    r.raise_for_status()
    data = r.json()
    traces = data.get("data", data) if isinstance(data, dict) else data
    print(f"=== {len(traces)} recent traces ===")
    for t in traces:
        sess = (t.get("session_id") or "-")[:10]
        print(
            f"  id={t['id'][:12]}  name={t.get('name', '?')[:30]:30}  session={sess}  ts={t.get('timestamp')}"
        )

    # fetch full detail (with observations) for the most recent few
    for t in traces[:4]:
        tid = t["id"]
        r = httpx.get(f"{BASE}/api/public/traces/{tid}", headers=headers, timeout=30)
        r.raise_for_status()
        detail = r.json()
        obs = detail.get("observations", [])
        print(
            f"\n=== TRACE {tid[:12]}  name={detail.get('name')}  session={detail.get('session_id')} ==="
        )
        print(f"    observations: {len(obs)}")
        for o in obs:
            print(
                f"    - {o.get('name', '?')[:40]:40} "
                f"type={o.get('type', '?'):11} "
                f"status={o.get('status', '?'):8} "
                f"start={o.get('start_time', '')[:23]} "
                f"end={(o.get('end_time') or '-')[:23]}"
            )
            # show error/level if any
            lvl = o.get("level")
            if lvl and lvl != "DEFAULT":
                print(f"        LEVEL={lvl}  output={str(o.get('output', ''))[:120]}")


if __name__ == "__main__":
    main()
