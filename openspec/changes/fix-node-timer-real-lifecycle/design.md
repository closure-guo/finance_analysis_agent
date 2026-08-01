# Design: fix-node-timer-real-lifecycle

## 问题机制

LangGraph `updates` 流：节点执行完毕后，才将该节点的状态更新作为一个 chunk 发出。因此"节点开始"在 updates 流中**不可观测**——只能在下一个 chunk（下一节点）到达时间接推断。

现有实现把 node_start 与 node_complete 都绑在"消费该节点 chunk"这一时刻，二者时间戳相等 → 快速节点 durationMs=0。

## 方案：节点真实生命周期事件

利用 `stream_mode=["updates","custom"]` 双模式（项目已用于 thinking_token）。custom 流由节点内的 `get_stream_writer()` **实时**写出，可在节点入口/出口发出真实时间戳。

### 1. timed_node 装饰器（nodes/_timing.py 新模块）

```python
from langgraph.config import get_stream_writer
import time, functools

def timed_node(node_id):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(state, *args, **kwargs):
            writer = get_stream_writer()
            t0 = time.time()
            writer({"type": "node_start", "node": node_id, "ts": int(t0 * 1000)})
            result = fn(state, *args, **kwargs)
            t1 = time.time()
            writer({"type": "node_end", "node": node_id,
                    "ts": int(t1 * 1000), "duration_ms": int((t1 - t0) * 1000)})
            return result
        return wrapper
    return deco
```

- **零侵入业务**：装饰器只包裹计时观测，不改节点签名与返回值。
- **并行安全**：`get_stream_writer()` 在 Send 扇出的并行子图中各自绑定正确节点上下文（LangGraph 保证 custom 事件携带其发出节点的 namespace）。
- 节点为同步函数，计时用 `time.time()` 简单直接。

### 2. 节点注册统一包裹（graph.py）

不逐个改节点文件，在 `build_5layer_graph` 的 `add_node` 处统一包裹：

```python
g.add_node("check_cache", timed_node("check_cache")(check_cache))
```

22 个节点统一处理，避免 22 处手工改动的不一致。

### 3. custom 事件处理（agent_factory.py）

`_make_run_deep_analysis` 的 custom 分支当前只处理 `chunk["type"] == "thinking"`。扩展：

```python
if mode == "custom":
    ctype = chunk.get("type")
    if ctype == "thinking": ...  # 现有
    elif ctype == "node_start":
        # 记录后端真实开始时间戳，暂存 pending_starts[node]
    elif ctype == "node_end":
        # 记录后端真实结束时间戳与 duration
```

**关键设计**：custom 的 node_start/node_end 在节点**真实生命周期**到达（早于对应 updates chunk）。updates chunk 到达时仍按现有逻辑 yield node_start（去重）+ node_complete，但**附加后端真实时间戳** `server_start_ts`/`server_end_ts`/`server_duration_ms` 到 metadata。SSE 透传这些字段。

这样：
- updates 流的 node_complete 仍负责 output 提取、completed/progress 计算（不变）
- custom 流提供真实时间戳，updates 流负责业务载荷
- 两流通过 node_id 关联

### 4. 前端时间戳策略（pipelineTree.ts）

```typescript
export function applyNodeEvent(tree, event, nowMs) {
  // node_start：优先 server_start_ts（后端真实入口），回退 nowMs
  const startTs = event.server_start_ts ?? nowMs
  // node_complete：优先 server_end_ts / server_duration_ms，回退 nowMs 计算
  const duration = event.server_duration_ms ?? (nowMs - startedAt)
}
```

- 有 server_* 时用后端真实值（快速节点显示真实毫秒→前端 formatDurationMs 截断为 0:00 属正确）
- 无 server_*（stub/fast path/历史会话）回退现有 Date.now() 逻辑 → **零回归**

### 5. SSE 契约

node_complete SSE 新增字段（可选，向后兼容）：
```json
{ "type": "node_complete", "node_id": "check_cache", ...,
  "server_start_ts": 1728000000100, "server_end_ts": 1728000000120, "server_duration_ms": 20 }
```

## 并行分析师的时间戳归属

Send 扇出 4 分析师并行：各自 custom 事件携带正确 node namespace（LangGraph 保证），互不错位。updates chunk 键即节点名（Delta 2 已验证），node_id 关联可靠。

## 测试策略

- **后端单测**：timed_node 包裹的节点 yield 出 node_start/node_end custom 事件且 ts 单调递增、duration>=0；`_make_run_deep_analysis` 将 server 时间戳附加到 node_complete metadata。
- **前端单测**：applyNodeEvent 优先 server_ts；缺失回退 Date.now()；快速节点 durationMs=server_duration_ms。
- **E2E**：stub 管线 node 无 server_ts 时回退正常（现有 17 用例不回归）；新增用例断言快速节点耗时来自 server_duration_ms（可在 TESTING=1 下给 stub 节点注入 server_ts 验证前端取值逻辑）。

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| custom 与 updates 流交错破坏 thinking_token 的 node 分组 | 两流独立处理，custom 的 node_start/end 不进 nodeTimelines；thinking_token 逻辑不变 |
| Send 并行子图 get_stream_writer 上下文错乱 | LangGraph 官方保证并行节点 custom 事件 namespace 正确；单测覆盖 4 分析师并行 |
| 装饰器遗漏节点 | 统一在 graph.py add_node 处包裹，单测断言全部 22 节点均被包裹 |
| fast path 无双流 | fast path 本就串行 await，时间戳真实，不改动 |
