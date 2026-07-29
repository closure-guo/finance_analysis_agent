"""临时验证脚本：stub 管线（TESTING=1）下 build_5layer_graph 是否产出 node_start/node_end custom 事件。

运行：TESTING=1 uv run python tests/scripts/verify_node_timing_stub.py
"""

import os

os.environ["TESTING"] = "1"
os.environ["STUB_NODE_DELAY"] = "0.05"

from finance_agent.graph import build_5layer_graph

initial = {
    "stock_code": "600519",
    "stock_name": "贵州茅台",
    "analysis_type": "standard",
    "peer_codes": [],
    "enable_web_search": False,
    "messages": [],
}

graph = build_5layer_graph()
node_starts = []
node_ends = []
updates_nodes = []

for mode, chunk in graph.stream(
    initial, config={"recursion_limit": 100}, stream_mode=["updates", "custom"]
):
    if mode == "custom" and isinstance(chunk, dict):
        t = chunk.get("type")
        if t == "node_start":
            node_starts.append(chunk["node"])
        elif t == "node_end":
            node_ends.append((chunk["node"], chunk.get("duration_ms")))
    elif mode == "updates":
        updates_nodes.extend(chunk.keys())

print("custom node_start 节点:", node_starts)
print("custom node_end (node, duration_ms):", node_ends)
print("updates 节点:", updates_nodes)
print("分析师 node_end:", [e for e in node_ends if "analyst" in e[0]])
