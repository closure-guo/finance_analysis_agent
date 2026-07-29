# Task 5.5 报告：ReAct 主链路快照接入（agent_factory.run_deep_analysis）

- **Status:** DONE
- **Commit:** a37c704 `feat: [agent] ReAct 主链路管线快照与会话状态兜底`

## 实施内容

在 `run_deep_analysis` 工具（`_make_run_deep_analysis` 返回的异步生成器）内维护管线
快照与会话状态兜底，覆盖 design.md §8 第 1 层。事件流完全不变。

1. **快照初始化**：工具入口（session_id 非空时）`build_layer_tree()` 建初始树，
   `_track_snapshot = bool(session_id)` 控制全部写入；session_id 为空时行为与现状一致。
2. **状态兜底**：
   - 入口：`update_session_status(session_id, "running")`
   - 主循环整体包 `try/except`：异常 → 置 `failed` 后 `raise`（re-raise）
   - 循环正常结束（组装 report metadata 前）：写最终快照 + 置 `completed`
3. **快照写入事件点**（与 PipelineRunner._run 同契约，三类事件各 apply + 落库）：
   - updates 流节点首现发 node_start 时：`{"type":"node_start","node_id",server_start_ts?}`
   - updates 流发 node_complete 时：`{"type":"node_complete","node_id","output"}`
   - custom 流 node_end 发 node_timing 时：`{"type":"node_timing","node_id","server_start_ts","server_end_ts","server_duration_ms"}`
   - 快照结构 `{"layerTree","currentNodeId","progress","updatedAt"}` 经
     `session_store.update_pipeline_snapshot` 落库。
4. **session_id 传入**：`_make_run_deep_analysis(..., session_id=...)` 形参已存在，
   `build_agent` deep 分支（agent_factory.py:540）已传 `kwargs.get("session_id")`，
   本任务未改 build_agent。

## `_current_node`/`_progress` 复用方式（brief 要求说明）

brief 给出二选一：在 pipeline_runner 暴露公开函数，或在 agent_factory 内联等价逻辑。
实际采用**第三种更简路径**：直接从 `finance_agent.pipeline_runner` import 私有函数
`_current_node`/`_progress`（同包内模块，Python 社区惯例允许，pipeline_runner.py 自身
在 `mark_swept_failed` 也跨模块复用 `session_store._get_db` 私有函数，属项目既有模式）。
理由：
- 二者是纯函数、语义稳定，内联复制会制造双份真相（前端语义等价逻辑已三处：前端 TS /
  pipeline_runner / 若再内联则第四份）；
- 提为公开函数会扩大 pipeline_runner 公开面，却无第二个外部消费方（YAGNI）。
未改 `pipeline_runner.py` 一行。

## TDD 证据

### RED（实现前）

`uv run pytest tests/test_react_pipeline_snapshot.py -v` → 4 failed, 2 passed：

- `test_snapshot_progresses_during_consumption` FAILED（pipeline_snapshot 为 None）
- `test_status_transitions_to_completed` FAILED（status 停留 running）
- `test_status_running_during_execution` FAILED（入口未置 running，观测为 pending）
- `test_exception_marks_failed_and_reraises` FAILED（异常后 status 停留 running）
- 2 个事件流基线用例（`test_event_stream_unchanged`、`test_no_session_id_skips_snapshot`）
  在实现前即通过——它们是无快照逻辑的基线行为，作为回归护栏保留。

### GREEN（实现后）

`uv run pytest tests/test_react_pipeline_snapshot.py -v` → **6 passed**（4.20s）。

事件流不变断言：sse_type 序列严格等于
`[node_start, node_complete, node_timing, node_start, node_complete, node_timing, report_ready]`。

## 连带回归

`uv run pytest tests/test_pipeline_runner.py tests/test_session_store.py tests/test_api_pipeline_resume.py -q`
→ **10 passed**（6.80s），无连带影响。

`uv run ruff check src/finance_agent/agent_factory.py` → All checks passed
（pre-commit ruff-format 重排了函数内 import 顺序，已随 commit 落定，最终再验通过）。

## Files changed

- `src/finance_agent/agent_factory.py`（+ 快照/状态逻辑，主循环包 try/except，import 排序）
- `tests/test_react_pipeline_snapshot.py`（新建，6 用例）
- 未改 `pipeline_runner.py`、`api.py`、前端。

## Self-review

- 完整性：brief 接口契约 4 项（3 类快照事件 + 状态三态兜底）全部落地；测试要求 4 项全覆盖，
  另加 2 项基线护栏。
- YAGNI：未动事件流、未动 build_agent、未扩大 pipeline_runner 公开面。
- 测试真实性：stub 仅替换 `_stream_graph`（同步事件源），真实走 executor 线程 +
  chunk_queue + 真实 session_store SQLite（tmp_path 隔离），无 mock 被测逻辑。
- async 驱动：用 `asyncio.run()` 在同步测试内驱动（brief 提示的 pytest-asyncio 兼容规避），
  实测 pyproject `asyncio_mode=auto` 下亦稳定。

## Concerns

1. **api.py 终局状态覆盖**：ReAct 路径正常结束时，api.py 的 `on_metadata`/落库逻辑也会
   写会话状态（既有行为）。本工具的 `completed` 写入发生在 report_ready metadata 组装前，
   时序上先于 api 终局写库，最终一致，无冲突；但两处都在写 status，若未来 api 侧改终局
   状态机需同步审视（设计内已接受，design.md §8 第 1 层定性为「兜底」）。
2. **会话尚未创建的理论窗口**：若 run_deep_analysis 触发时 session 行尚不存在，
   `update_session_status`/`update_pipeline_snapshot` 返回 False 静默跳过（不影响事件流）。
   实际链路 session 先于 agent 创建，未在测试覆盖该窗口（属理论路径）。

## Fix Round 1: layerTree 序列化契约对齐

### 问题

快照契约要求 `pipeline_snapshot` 的 JSON 中 `layerTree` 字段为**内嵌的序列化 JSON
字符串**（前端 `frontend/src/types.ts` 中 `PipelineSnapshot.layerTree: string`，
`App.tsx` 多处 `deserializeLayerTree(snapshot.layerTree)` 对其二次解析）。

但后端两处写入点均写成了**对象数组**（`list[dict]`）：

- `src/finance_agent/pipeline_runner.py` `_run` 内快照写入（原约 296 行）：`"layerTree": tree`
- `src/finance_agent/agent_factory.py` `_persist_snapshot`（原约 296 行）：`"layerTree": tree`

后果：前端 `deserializeLayerTree` 收到对象数组而非字符串 -> `JSON.parse` 失败 ->
回退初始空树 -> 切回历史会话恢复成空时间轴。

### 修复

两处写入点改为 `json.dumps(tree, ensure_ascii=False)`，使 `layerTree` 成为序列化
JSON 字符串，与前端契约对齐。两个文件顶部均已 `import json`，无需新增导入。

- `src/finance_agent/pipeline_runner.py`：`"layerTree": json.dumps(tree, ensure_ascii=False)`
- `src/finance_agent/agent_factory.py`：同上

### 测试同步更新（保持契约一致）

将相关断言改为「外层解析后 layerTree 仍是字符串，再次解析才是树」：

- `tests/test_pipeline_runner.py` `test_snapshot_tracks_node_completion`：
  `tree = json.loads(snap["layerTree"])` 后再遍历子节点。
- `tests/test_react_pipeline_snapshot.py` `_snapshot_node_status`：同上二次解析。
- `tests/test_api_pipeline_resume.py` 两处 `done_nodes` 推导（`test_pipeline_continues_after_sse_disconnect`
  与 `test_pipeline_snapshot_persists_after_completion`）：同上二次解析。
- `tests/test_session_store.py`：不改（`update_pipeline_snapshot` 接收任意 dict，
  不校验内部结构，`layerTree` 占位为 `[]` 不涉及树结构）。

### TDD 证据

**RED（实现未改，断言已切到字符串契约）**：

`uv run pytest tests/test_pipeline_runner.py tests/test_react_pipeline_snapshot.py tests/test_api_pipeline_resume.py -v`
-> 4 failed, 10 passed：

- `test_snapshot_tracks_node_completion` FAILED
- `test_snapshot_progresses_during_consumption` FAILED
- `test_pipeline_continues_after_sse_disconnect` FAILED
- `test_pipeline_snapshot_persists_after_completion` FAILED

失败均为 `TypeError: the JSON object must be str, bytes or bytearray, not list`
（`json.loads(snap["layerTree"])` 收到 list），正是前端 `deserializeLayerTree` 收到
对象数组而非字符串的同款症状。

**GREEN（两处写入点改为 json.dumps 后）**：

`uv run pytest tests/test_pipeline_runner.py tests/test_react_pipeline_snapshot.py tests/test_api_pipeline_resume.py tests/test_session_store.py -v`
-> **16 passed**（6.97s）。

`uv run ruff check src/finance_agent/pipeline_runner.py src/finance_agent/agent_factory.py`
-> All checks passed。

### Files changed

- `src/finance_agent/pipeline_runner.py`（`_run` 快照 layerTree 序列化为 JSON 字符串）
- `src/finance_agent/agent_factory.py`（`_persist_snapshot` 同上）
- `tests/test_pipeline_runner.py`（layerTree 断言二次解析）
- `tests/test_react_pipeline_snapshot.py`（同上）
- `tests/test_api_pipeline_resume.py`（两处断言二次解析）
