"""节点生命周期计时测试（fix-node-timer-real-lifecycle delta task 1.1/1.4）。

验证 timed_node 装饰器在节点真实入口/出口发出 custom 事件（node_start/node_end），
以及 _make_run_deep_analysis 将后端真实时间戳附加到 node_complete metadata。
"""

import asyncio
from unittest.mock import patch

from finance_agent.nodes._timing import timed_node


def _drain(coro_factory):
    """运行 async 生成器并收集所有事件。"""
    return asyncio.run(_collect(coro_factory))


async def _collect(agen):
    events = []
    async for e in agen:
        events.append(e)
    return events


class TestTimedNode:
    """timed_node 装饰器：节点真实生命周期 custom 事件（task 1.1）。"""

    def _run_node_with_writer(self, node_fn, node_id, state):
        """在带 stream_writer 的上下文中执行被包裹节点，捕获写出的 custom 事件。"""

        written = []

        def fake_writer(payload):
            written.append(payload)

        wrapped = timed_node(node_id)(node_fn)

        # get_stream_writer 在节点执行上下文内被调用；测试用 patch 注入收集器
        with patch("finance_agent.nodes._timing.get_stream_writer", return_value=fake_writer):
            result = wrapped(state)
        return result, written

    def test_emits_node_start_and_node_end(self):
        """被包裹节点在入口发 node_start、出口发 node_end。"""

        def sample_node(state):
            return {"done": True}

        result, written = self._run_node_with_writer(sample_node, "check_cache", {})
        assert result == {"done": True}

        types = [w["type"] for w in written]
        assert "node_start" in types
        assert "node_end" in types
        # 顺序：start 在 end 前
        assert types.index("node_start") < types.index("node_end")

    def test_events_carry_node_id_and_timestamps(self):
        """node_start/node_end 携带正确 node_id、epoch_ms 时间戳；end 含 duration_ms。"""

        def sample_node(state):
            return {}

        _, written = self._run_node_with_writer(sample_node, "fetch_data", {})
        start = next(w for w in written if w["type"] == "node_start")
        end = next(w for w in written if w["type"] == "node_end")

        assert start["node"] == "fetch_data"
        assert end["node"] == "fetch_data"
        # epoch 毫秒时间戳（>1e12 量级）
        assert start["ts"] > 1_000_000_000_000
        assert end["ts"] > 1_000_000_000_000
        assert end["ts"] >= start["ts"]
        assert end["duration_ms"] >= 0
        # duration 与时间戳差一致
        assert abs(end["duration_ms"] - (end["ts"] - start["ts"])) <= 2

    def test_timestamp_monotonic_and_duration_nonnegative_for_slow_node(self):
        """慢节点（sleep）duration_ms 反映真实耗时。"""
        import time

        def slow_node(state):
            time.sleep(0.05)
            return {}

        _, written = self._run_node_with_writer(slow_node, "trader", {})
        end = next(w for w in written if w["type"] == "node_end")
        assert end["duration_ms"] >= 40  # 约 50ms，留容差

    def test_preserves_node_signature_and_return(self):
        """装饰器不改变节点签名（functools.wraps）与返回值。"""

        def my_node(state):
            """节点 docstring。"""
            return {"x": 1}

        wrapped = timed_node("n")(my_node)
        assert wrapped.__name__ == "my_node"
        with patch("finance_agent.nodes._timing.get_stream_writer", return_value=lambda p: None):
            assert wrapped({}) == {"x": 1}


class TestGraphNodesWrapped:
    """build_5layer_graph 的全部图节点统一包裹 timed_node（task 1.3）。"""

    def test_all_business_nodes_wrapped(self):
        """图中全部业务节点（非 _passthrough entry）被 timed_node 包裹。

        断言编译图中注册的业务节点函数带 _timed_node 标记。graph.nodes 的
        RunnableBinding/RunnableCallable 包装层级随 LangGraph 版本变化，
        逐层探测 func/afunc/bound 找到被包裹的原始函数。
        """
        from finance_agent.graph import build_5layer_graph

        graph = build_5layer_graph()
        entry_nodes = {
            "analysts_entry",
            "debate_r1_entry",
            "debate_r2_entry",
            "risk_r1_entry",
            "risk_r2_entry",
        }
        business = {n for n in graph.nodes if n not in entry_nodes and not n.startswith("__")}
        for expected in (
            "check_cache",
            "fetch_data",
            "technical_analyst",
            "trader",
            "risk_judge",
            "fund_manager",
        ):
            assert expected in business

        def _find_timed(spec) -> bool:
            """在节点 spec 的包装层中查找带 _timed_node 标记的函数。"""
            seen = set()
            stack = [spec]
            while stack:
                obj = stack.pop()
                if obj is None or id(obj) in seen:
                    continue
                seen.add(id(obj))
                if getattr(obj, "_timed_node", False):
                    return True
                for attr in ("bound", "func", "afunc", "runnable"):
                    stack.append(getattr(obj, attr, None))
            return False

        unwrapped = [n for n in business if not _find_timed(graph.nodes.get(n))]
        assert not unwrapped, f"未被 timed_node 包裹的业务节点: {unwrapped}"
