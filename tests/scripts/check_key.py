import os

k = os.environ.get("TAVILY_API_KEY", "")
print(f"Key set: {bool(k)}, len={len(k)}, prefix={k[:6] if k else ''}")
