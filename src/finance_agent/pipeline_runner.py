"""会话级管线后台执行器。

graph.stream 是同步生成器，用独立线程执行，与 SSE 订阅解耦：
客户端断开仅停止订阅，后台线程继续推进管线。
进度快照（layerTree JSON）在每节点事件时持久化到 sessions.pipeline_snapshot，
SSE 端通过 get_events 轮询拉取累积事件。
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Callable, Generator

from finance_agent import session_store

logger = logging.getLogger(__name__)

_SSE_DATA_RE = re.compile(r"^data: (.*)$", re.MULTILINE)

# 与前端 pipelineTree.LAYER_TREE_CONFIG 对齐的 节点 -> layer 映射。
# 由 api._NODE_MAP 惰性派生（避免模块级循环导入）。
_NODE_TO_LAYER: dict[str, str] | None = None
_LAYER_ORDER: list[str] | None = None


def _node_layer_map() -> tuple[dict[str, str], list[str]]:
    global _NODE_TO_LAYER, _LAYER_ORDER
    if _NODE_TO_LAYER is None:
        from finance_agent.api import _ALL_NODES, _NODE_MAP

        _NODE_TO_LAYER = {nid: info["layer"] for nid, info in _NODE_MAP.items()}
        # layer 顺序按节点出现顺序去重
        order: list[str] = []
        for nid in _ALL_NODES:
            layer = _NODE_TO_LAYER.get(nid)
            if layer and layer not in order:
                order.append(layer)
        _LAYER_ORDER = order
    return _NODE_TO_LAYER, _LAYER_ORDER  # type: ignore[return-value]


# ── layerTree 快照维护（与前端 pipelineTree.applyNodeEvent 语义等价）──


def build_layer_tree() -> list[dict]:
    """构建初始 layerTree（与前端 buildLayerTree 等价）。"""
    node_to_layer, layer_order = _node_layer_map()
    layers: dict[str, list[str]] = {layer: [] for layer in layer_order}
    from finance_agent.api import _ALL_NODES, _NODE_MAP

    for nid in _ALL_NODES:
        info = _NODE_MAP.get(nid)
        if info:
            layers[info["layer"]].append(nid)
    return [
        {
            "id": layer,
            "label": layer,
            "status": "pending",
            "children": [
                {"nodeId": nid, "label": nid, "status": "pending"} for nid in layers[layer]
            ],
        }
        for layer in layer_order
    ]


def apply_node_event(tree: list[dict], event: dict, now_ms: int) -> list[dict]:
    """应用 node_start/node_complete/node_timing 事件（与前端语义等价，不可变更新）。"""
    node_to_layer, _ = _node_layer_map()
    layer_id = node_to_layer.get(event.get("node_id", ""))
    if not layer_id:
        return tree

    new_tree = []
    for layer in tree:
        if layer["id"] != layer_id:
            new_tree.append(layer)
            continue
        children = []
        for child in layer["children"]:
            if child["nodeId"] != event["node_id"]:
                children.append(child)
                continue
            etype = event["type"]
            # node_timing：只更新时间戳/耗时，不改状态（不受 completed 不回退限制）
            if etype == "node_timing":
                started = event.get("server_start_ts", child.get("startedAt"))
                duration = event.get("server_duration_ms")
                if (
                    duration is None
                    and event.get("server_end_ts") is not None
                    and started is not None
                ):
                    duration = max(0, event["server_end_ts"] - started)
                else:
                    duration = duration if duration is not None else child.get("durationMs")
                children.append(
                    {
                        **child,
                        "startedAt": started,
                        "completedAt": event.get("server_end_ts", child.get("completedAt")),
                        "durationMs": duration,
                    }
                )
                continue
            # 状态单调：completed 不回退
            if child.get("status") == "completed":
                children.append(child)
                continue
            if etype == "node_start":
                started = event.get("server_start_ts", child.get("startedAt", now_ms))
                children.append({**child, "status": "running", "startedAt": started})
            else:  # node_complete
                started = event.get("server_start_ts", child.get("startedAt", now_ms))
                children.append(
                    {
                        **child,
                        "status": "completed",
                        "startedAt": started,
                        "completedAt": now_ms,
                        "durationMs": max(0, now_ms - started),
                        "output": event.get("output", child.get("output")),
                    }
                )
        # 推导 layer 状态：任一 running → running；全部 completed → completed
        any_running = any(c["status"] == "running" for c in children)
        all_completed = len(children) > 0 and all(c["status"] == "completed" for c in children)
        status = layer["status"]
        if status != "completed":
            if all_completed:
                status = "completed"
            elif any_running:
                status = "running"
        layer_started = layer.get("startedAt")
        if layer_started is None and (any_running or all_completed):
            layer_started = now_ms
        layer_completed = layer.get("completedAt")
        if status == "completed" and layer_completed is None:
            layer_completed = now_ms
        duration = layer.get("durationMs")
        if status == "completed" and layer_started is not None and layer_completed is not None:
            duration = max(0, layer_completed - layer_started)
        new_tree.append(
            {
                **layer,
                "status": status,
                "children": children,
                "startedAt": layer_started,
                "completedAt": layer_completed,
                "durationMs": duration,
            }
        )
    return new_tree


def _current_node(tree: list[dict]) -> str:
    for layer in tree:
        for child in layer["children"]:
            if child["status"] == "running":
                return child["nodeId"]
    return ""


def _progress(tree: list[dict]) -> float:
    total = sum(len(layer["children"]) for layer in tree)
    if total == 0:
        return 0.0
    done = sum(1 for layer in tree for c in layer["children"] if c["status"] == "completed")
    return done / total


# ── 后台执行器 ──


class _RunState:
    def __init__(self, thread: threading.Thread):
        self.thread = thread
        self.events: list[str] = []
        self.lock = threading.Lock()
        self.done = False


class PipelineRunner:
    """管线后台执行：事件累积 + 快照持久化。幂等 start。"""

    _running: dict[str, _RunState] = {}
    _guard = threading.Lock()

    @classmethod
    def is_running(cls, session_id: str) -> bool:
        with cls._guard:
            state = cls._running.get(session_id)
            return state is not None and not state.done

    @classmethod
    def start(
        cls,
        session_id: str,
        event_source: Callable[[], Generator[str, None, None]],
        initial_snapshot: dict,
    ) -> None:
        """启动后台管线线程。已在跑则幂等返回。"""
        with cls._guard:
            if session_id in cls._running and not cls._running[session_id].done:
                return
            thread = threading.Thread(
                target=cls._run,
                args=(session_id, event_source, initial_snapshot),
                daemon=True,
            )
            cls._running[session_id] = _RunState(thread)
            thread.start()

    @classmethod
    def get_events(cls, session_id: str) -> list[str]:
        """取走累积的 SSE 事件（消费式）。done 且取空后清理条目。"""
        with cls._guard:
            state = cls._running.get(session_id)
            if state is None:
                return []
            with state.lock:
                events, state.events = state.events, []
            if state.done and not state.events:
                cls._running.pop(session_id, None)
            return events

    @classmethod
    def _run(
        cls,
        session_id: str,
        event_source: Callable[[], Generator[str, None, None]],
        snapshot: dict,
    ) -> None:
        state = cls._running.get(session_id)
        tree = snapshot.get("layerTree") or build_layer_tree()
        try:
            for sse_str in event_source():
                if state is not None:
                    with state.lock:
                        state.events.append(sse_str)
                event = cls._parse_event(sse_str)
                if event is None:
                    continue
                if event.get("type") in ("node_start", "node_complete", "node_timing"):
                    now_ms = int(time.time() * 1000)
                    tree = apply_node_event(tree, event, now_ms)
                    snapshot = {
                        "layerTree": tree,
                        "currentNodeId": _current_node(tree),
                        "progress": _progress(tree),
                        "updatedAt": now_ms,
                    }
                    session_store.update_pipeline_snapshot(session_id, snapshot)
        except Exception:
            logger.exception("后台管线执行异常 session=%s", session_id)
            session_store.update_session_status(session_id, "failed")
        finally:
            if state is not None:
                state.done = True

    @staticmethod
    def _parse_event(sse_str: str) -> dict | None:
        match = _SSE_DATA_RE.search(sse_str)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None

    @classmethod
    def mark_swept_failed(cls, statuses: tuple[str, ...] = ("running",)) -> int:
        """启动清扫：悬挂 running 会话置 failed（后端重启后 _running 已丢失）。"""
        conn = session_store._get_db()  # noqa: SLF001 - 同模块内部复用连接工厂
        cur = conn.execute(
            f"UPDATE sessions SET status = 'failed' WHERE status IN ({','.join('?' * len(statuses))})",  # noqa: S608
            tuple(statuses),
        )
        conn.commit()
        conn.close()
        return cur.rowcount
