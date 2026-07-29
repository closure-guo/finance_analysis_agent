"""节点生命周期计时装饰器（fix-node-timer-real-lifecycle delta task 1.2）。

timed_node 包裹图节点，在节点真实入口/出口通过 get_stream_writer() 发出
custom 事件（node_start/node_end），携带后端真实 epoch_ms 时间戳与耗时。

设计要点：
- 零侵入业务：只包裹计时观测，不改节点签名与返回值（functools.wraps）。
- 并行安全：get_stream_writer() 在 Send 扇出的并行子图中各自绑定正确节点
  上下文，custom 事件 namespace 由 LangGraph 保证。
- 与 updates 流互补：custom 流提供真实时间戳，updates 流负责 output 提取与
  completed/progress 计算；两流通过 node_id 关联（见 agent_factory）。
"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable

from langgraph.config import get_stream_writer


def timed_node(node_id: str) -> Callable:
    """包裹图节点，在真实入口/出口发出 node_start/node_end custom 事件。

    Args:
        node_id: 节点 ID（与 add_node 注册名一致，用于前端按节点归属计时）。

    Returns:
        装饰器：包裹后的节点函数带 `_timed_node = True` 标记（供测试断言全部包裹）。
    """

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(state: dict, *args, **kwargs):
            writer = get_stream_writer()
            t0 = time.time()
            writer({"type": "node_start", "node": node_id, "ts": int(t0 * 1000)})
            result = fn(state, *args, **kwargs)
            t1 = time.time()
            writer(
                {
                    "type": "node_end",
                    "node": node_id,
                    "ts": int(t1 * 1000),
                    "duration_ms": int((t1 - t0) * 1000),
                }
            )
            return result

        wrapper._timed_node = True  # type: ignore[attr-defined]
        return wrapper

    return deco
