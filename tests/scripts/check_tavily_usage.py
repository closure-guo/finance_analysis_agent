"""检查 Tavily API 用量与配额（手动验证脚本）。

调用 GET https://api.tavily.com/usage 查询当前 API Key 的用量与上限。
用法: uv run python tests/scripts/check_tavily_usage.py
"""

from __future__ import annotations

import json
import os
import urllib.request


def main() -> int:
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        print("TAVILY_API_KEY 未配置")
        return 1

    req = urllib.request.Request(
        "https://api.tavily.com/usage",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"调用 /usage 失败: {exc}")
        return 2

    print(json.dumps(data, indent=2, ensure_ascii=False))

    key_info = data.get("key", {})
    acct = data.get("account", {})
    usage = key_info.get("usage")
    limit = key_info.get("limit")
    if isinstance(usage, int) and isinstance(limit, int):
        remain = max(limit - usage, 0)
        print()
        print(f"Key 用量: {usage} / {limit}（剩余 {remain}）")
    elif isinstance(usage, int) and limit is None:
        print()
        print(f"Key 用量: {usage}（无上限 limit=null）")

    plan_usage = acct.get("plan_usage")
    plan_limit = acct.get("plan_limit")
    if isinstance(plan_usage, int) and isinstance(plan_limit, int):
        remain = max(plan_limit - plan_usage, 0)
        print(f"账户套餐用量: {plan_usage} / {plan_limit}（剩余 {remain}）")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
