"""Test macro and news data fetching."""

import sys

sys.path.insert(0, "src")

from finance_agent.data.akshare_client import AKShareClient

ak = AKShareClient()

# Test macro
print("=== Macro Indicators ===")
macro = ak.fetch_macro_indicators()
print(f"Keys: {list(macro.keys())}")
for k, v in macro.items():
    if isinstance(v, list):
        print(f"  {k}: {len(v)} records")
        if v:
            print(f"    sample: {v[0]}")
    else:
        print(f"  {k}: {v}")

# Test news
print("\n=== News ===")
news = ak.fetch_news("600519")
print(f"Articles: {len(news)}")
if news:
    for i, n in enumerate(news[:3]):
        print(f"  [{i + 1}] {n.get('title', '')[:60]}")
        print(f"      time: {n.get('datetime', '')}  source: {n.get('source', '')}")
