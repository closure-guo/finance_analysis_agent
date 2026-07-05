"""Test 4 analysts in the 5-layer pipeline."""

import json

import requests

resp = requests.post(
    "http://127.0.0.1:8000/api/analyze",
    json={
        "query": "600519",
        "api_key": "",
    },
    stream=True,
    timeout=300,
)

analyst_reports = []
for line in resp.iter_lines():
    if not line:
        continue
    line = line.decode()
    if line.startswith("data: "):
        event = json.loads(line[6:])
        etype = event.get("type", "")

        if etype == "progress":
            step = event.get("step", "")
            status = event.get("status", "")
            print(f"[{status}] {step}")

        elif etype == "analyst":
            name = event.get("agent_name", "")
            summary = event.get("summary", "")[:80]
            print(f"  -> analyst [{name}]: {summary}")
            analyst_reports.append(name)

        elif etype == "report":
            report = event.get("report", "")
            # Check for analyst sections
            for name in ["技术面", "宏观", "基本面", "舆情"]:
                if name in report:
                    print(f"  [report contains '{name}' section]")
            print(f"  Report length: {len(report)} chars")

        elif etype == "done":
            print("\n=== Done ===")
            print(f"Analyst reports found: {analyst_reports}")
            break

        elif etype == "error":
            print(f"[ERROR] {event.get('message', '')}")
            break
