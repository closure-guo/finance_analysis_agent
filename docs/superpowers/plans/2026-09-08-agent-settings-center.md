# Agent 设置中心 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建设置中心页 `/settings`（左侧垂直导航），聚合 LLM 配置 / 缓存管理 / 会话管理 / 运行信息 / 数据监控 / 战绩展示偏好六大分区，并将原 `SettingsModal` 弹窗整体迁移为页内「LLM 配置」分区。

**Architecture:** 后端新增最小、只读/显式清理端点（缓存统计/清理、会话批量清空、run-info、数据源状态），全部新增不破坏既有端点；`DataCache`/`ProbeCache`/`session_store` 补只读与清理方法并复用既有锁/事务。前端沿用现有 pathname 路由，新增 `pages/settings/` 设置中心页与各分区组件，抽 `LlmConfigPane` 复用现有 LLM 配置表单逻辑，战绩偏好存 localStorage 由战绩页消费。

**Tech Stack:** 后端 Python 3.12 / FastAPI / SQLite / LiteLLM；前端 React 18 / Vite / TypeScript / Tailwind（shadcn 原语 + 语义令牌）/ Vitest。

## Global Constraints

- 前端变量命名 camelCase；代码注释中文。
- 后端 `DataCache`/`ProbeCache`/`session_store` 保持既有锁/事务模式；阻塞 DB 调用一律 `await asyncio.to_thread(...)`。
- 任一新增端点均**不得回显 apiKey**；`GET /api/run-info` 沿用 `GET /api/llm-config` 的不回显约束（硬红线）。
- 数据源监控埋点**不得改变** `nodes/fetch.py` 的重试/降级/回退/取消/超时逻辑，只加计数。
- 后端必须单 uvicorn worker（StreamRegistry 进程内）；进程内计数器/单例语义依赖此约定。
- `cache.db` 业务类别从 **key 后缀** 解析（`{code}:{suffix}`，全局键 `benchmark_kline`/`macro_indicators` 无前缀）；`cache` 表的 `data_type` 列只存 `json`/`dataframe`，不是业务类别，**禁止**用该列做业务分类。
- 工作树 `data/cache.py`、`nodes/cache.py`、`nodes/fetch.py` 已有未提交改动，所有编辑必须在其之上增量，勿回退。
- 无鉴权；E2E 禁止 mock 被测系统；交互类变更 E2E 门禁按 project-workflow §3 Step 4.5 生效状态执行。

---

### Task 1: DataCache 统计与清理方法

**Files:**
- Modify: `src/finance_agent/data/cache.py`
- Test: `tests/data/test_cache.py`

**Interfaces:**
- Consumes: 现有 `DataCache.__init__`（`db_path="cache.db"`）、`self._lock`（`threading.RLock`）、`self._conn`。
- Produces:
  - `DataCache.stats() -> dict`：`{entries:int, bytes:int, expired:int, permanent:int, per_type:list[dict]}`；`per_type[i]` = `{category:str, entries:int, bytes:int, earliest_expire:float|None}`。
  - `DataCache.clear_all() -> int`（删除行数）。
  - `DataCache.delete_by_code(code: str) -> int`（`{code}:%`）。
  - `DataCache.delete_by_type(category: str) -> int`（key 后缀 == category，或整 key == category）。

- [ ] **Step 1: 写失败测试**

在 `tests/data/test_cache.py` 追加（沿用既有 `tmp_path` fixture）：

```python
def test_stats_reports_per_type_and_totals(cache: DataCache):
    cache.set("600519:stock_quote", {"price": 100}, ttl_seconds=3600)
    cache.set("600519:kline", {"x": 1}, ttl_seconds=3600)
    cache.set("000001:stock_quote", {"price": 50})  # 永久
    s = cache.stats()
    assert s["entries"] == 3
    assert s["permanent"] == 1
    cats = {p["category"]: p["entries"] for p in s["per_type"]}
    assert cats["stock_quote"] == 2
    assert cats["kline"] == 1

def test_stats_counts_expired(cache: DataCache):
    import time
    cache.set("600519:news", {"n": 1}, expire_at=time.time() - 10)
    s = cache.stats()
    assert s["expired"] == 1

def test_clear_all_and_delete_by_code(cache: DataCache):
    cache.set("600519:news", {"n": 1})
    cache.set("000001:news", {"n": 2})
    assert cache.delete_by_code("600519") == 1
    assert cache.keys() == ["000001:news"]
    assert cache.clear_all() == 1
    assert cache.keys() == []

def test_delete_by_type_uses_key_suffix(cache: DataCache):
    cache.set("600519:kline", {"k": 1})
    cache.set("000001:stock_quote", {"q": 1})
    cache.set("benchmark_kline", {"b": 1})
    assert cache.delete_by_type("kline") == 1  # 只清 600519:kline，不动 benchmark_kline
    assert sorted(cache.keys()) == ["000001:stock_quote", "benchmark_kline"]
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/data/test_cache.py -k "stats or clear_all or delete_by" -v`
Expected: FAIL（`AttributeError: 'DataCache' object has no attribute 'stats'`）

- [ ] **Step 3: 最小实现**

在 `src/finance_agent/data/cache.py` 的 `keys()` 之后追加：

```python
def stats(self) -> dict:
    """返回数据缓存统计：总条目/占用/已过期/永久 + 按业务类别聚合。

    业务类别从 key 后缀解析（`{code}:{suffix}`，全局键无前缀取整 key）。
    """
    with self._lock:
        now = time.time()
        rows = self._conn.execute(
            "SELECT CASE WHEN instr(key, ':') > 0 "
            "THEN substr(key, instr(key, ':') + 1) ELSE key END AS cat, "
            "COUNT(*) AS n, SUM(LENGTH(data)) AS bytes, MIN(expire_at) AS earliest "
            "FROM cache GROUP BY cat"
        ).fetchall()
        per_type = []
        for r in rows:
            per_type.append({
                "category": r[0], "entries": r[1], "bytes": r[2], "earliest_expire": r[3],
            })
        expired = self._conn.execute(
            "SELECT COUNT(*) FROM cache WHERE expire_at IS NOT NULL AND expire_at < ?",
            (now,)).fetchone()[0]
        permanent = self._conn.execute(
            "SELECT COUNT(*) FROM cache WHERE expire_at IS NULL").fetchone()[0]
        return {
            "entries": sum(p["entries"] for p in per_type),
            "bytes": sum(p["bytes"] or 0 for p in per_type),
            "expired": expired,
            "permanent": permanent,
            "per_type": per_type,
        }

def clear_all(self) -> int:
    """清空全部数据缓存条目，返回删除行数。"""
    with self._lock:
        cur = self._conn.execute("DELETE FROM cache")
        self._conn.commit()
        return cur.rowcount

def delete_by_code(self, code: str) -> int:
    """删除某股票代码的全部缓存条目（`{code}:*`），返回删除行数。"""
    with self._lock:
        cur = self._conn.execute("DELETE FROM cache WHERE key LIKE ?", (f"{code}:%",))
        self._conn.commit()
        return cur.rowcount

def delete_by_type(self, category: str) -> int:
    """删除业务类别等于 category 的条目（key 后缀匹配，或整 key == category），返回删除行数。"""
    with self._lock:
        cur = self._conn.execute(
            "DELETE FROM cache WHERE (instr(key, ':') > 0 "
            "AND substr(key, instr(key, ':') + 1) = ?) OR key = ?",
            (category, category))
        self._conn.commit()
        return cur.rowcount
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/data/test_cache.py -k "stats or clear_all or delete_by" -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/data/test_cache.py src/finance_agent/data/cache.py
git commit -m "feat(cache): DataCache 统计与按类别/按代码/全清方法"
```

---

### Task 2: 数据源监控计数器模块

**Files:**
- Create: `src/finance_agent/data/monitoring.py`
- Test: `tests/data/test_monitoring.py`

**Interfaces:**
- Consumes: 无。
- Produces:
  - `DataSourceMonitor.record_hit()/record_miss()/record_fail(label: str)`：进程内计数（`label` 为数据类别后缀，如 `kline`）。
  - `DataSourceMonitor.snapshot() -> dict`：`{hits:int, misses:int, fails:dict[str,int], last_hit:float|None}`。
  - `get_monitor() -> DataSourceMonitor`（单例）、`reset_monitor_for_tests()`。

- [ ] **Step 1: 写失败测试**

创建 `tests/data/test_monitoring.py`：

```python
import pytest
from finance_agent.data.monitoring import DataSourceMonitor


@pytest.fixture(autouse=True)
def reset():
    from finance_agent.data.monitoring import reset_monitor_for_tests
    reset_monitor_for_tests()
    yield
    reset_monitor_for_tests()


def test_hit_miss_fail_and_last_hit():
    m = DataSourceMonitor()
    m.record_hit()
    m.record_hit()
    m.record_miss()
    m.record_fail("kline")
    m.record_fail("kline")
    snap = m.snapshot()
    assert snap["hits"] == 2
    assert snap["misses"] == 1
    assert snap["fails"] == {"kline": 2}
    assert snap["last_hit"] is not None


def test_get_monitor_singleton():
    from finance_agent.data.monitoring import get_monitor
    assert get_monitor() is get_monitor()
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/data/test_monitoring.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'finance_agent.data.monitoring'`）

- [ ] **Step 3: 最小实现**

创建 `src/finance_agent/data/monitoring.py`：

```python
"""数据源拉取监控：进程内命中/未命中/失败计数（非持久化，进程重启清零）。"""
import threading
import time


class DataSourceMonitor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._fails: dict[str, int] = {}
        self._last_hit: float | None = None

    def record_hit(self) -> None:
        with self._lock:
            self._hits += 1
            self._last_hit = time.time()

    def record_miss(self) -> None:
        with self._lock:
            self._misses += 1

    def record_fail(self, label: str) -> None:
        with self._lock:
            self._fails[label] = self._fails.get(label, 0) + 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "fails": dict(self._fails),
                "last_hit": self._last_hit,
            }


_monitor: DataSourceMonitor | None = None


def get_monitor() -> DataSourceMonitor:
    global _monitor
    if _monitor is None:
        _monitor = DataSourceMonitor()
    return _monitor


def reset_monitor_for_tests() -> None:
    global _monitor
    _monitor = None
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/data/test_monitoring.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/data/test_monitoring.py src/finance_agent/data/monitoring.py
git commit -m "feat(monitor): 数据源命中/未命中/失败进程内计数器"
```

---

### Task 3: check_cache / fetch_data 埋点（非侵入）

**Files:**
- Modify: `src/finance_agent/nodes/cache.py`、`src/finance_agent/nodes/fetch.py`
- Test: `tests/nodes/test_cache.py`、`tests/nodes/test_fetch.py`

**Interfaces:**
- Consumes: `get_monitor()`（Task 2）。
- Produces: 无新签名；在 HIT/MISS/失败处调用计数器。

- [ ] **Step 1: 写失败测试**

在 `tests/nodes/test_cache.py` 追加（沿用既有 `MagicMock` cache fixture 风格）：

```python
import pytest
from finance_agent.nodes.cache import check_cache
from finance_agent.data.monitoring import get_monitor, reset_monitor_for_tests


@pytest.fixture(autouse=True)
def reset_mon():
    reset_monitor_for_tests()
    yield
    reset_monitor_for_tests()


def test_check_cache_miss_records_miss():
    from unittest.mock import MagicMock
    cache = MagicMock()
    cache.get.return_value = None
    result = check_cache({"stock_code": "600519"}, cache=cache)
    assert result["cache_result"] == "MISS"
    assert get_monitor().snapshot()["misses"] == 1
```

在 `tests/nodes/test_fetch.py` 追加（仿既有 `mock_client`/`mock_cache` 风格，构造一次可复现的失败分支；若既有 fixture 已能让某 label 抛错，直接复用其 `except` 路径）：

```python
def test_fetch_failure_records_fail():
    from finance_agent.data.monitoring import get_monitor, reset_monitor_for_tests
    reset_monitor_for_tests()
    # 构造 mock client 使某可选 label 抛错，复用既有 mock 结构
    # （具体 mock 装配沿用本文件既有 fetch_data 测试的 mock_client 范式）
    ...
    assert get_monitor().snapshot()["fails"].get("news", 0) >= 1
    reset_monitor_for_tests()
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/nodes/test_cache.py tests/nodes/test_fetch.py -v`
Expected: FAIL（埋点缺失，断言计数为 0）

- [ ] **Step 3: 最小实现**

`nodes/cache.py` MISS 出口（现 `return {"cache_result": "MISS"}` 处）改为：

```python
        if val is None:
            get_monitor().record_miss()
            return {"cache_result": "MISS"}
```

HIT 出口（正常构造 result 后、`return result` 前）插入：

```python
    get_monitor().record_hit()
    return result
```

文件顶部加入 `from finance_agent.data.monitoring import get_monitor`。

`nodes/fetch.py` result-collect 循环的 `except Exception as e:` 分支最前面插入：

```python
        except Exception as e:
            get_monitor().record_fail(label)
            if obs:
                ...
```

文件顶部加入 `from finance_agent.data.monitoring import get_monitor`。

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/nodes/test_cache.py tests/nodes/test_fetch.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/nodes/test_cache.py tests/nodes/test_fetch.py \
  src/finance_agent/nodes/cache.py src/finance_agent/nodes/fetch.py
git commit -m "feat(monitor): check_cache/fetch 命中未命中失败埋点（不改逻辑）"
```

---

### Task 4: ProbeCache 统计

**Files:**
- Modify: `src/finance_agent/llm/probe_cache.py`
- Test: `tests/llm/test_probe_cache.py`

**Interfaces:**
- Consumes: 现有 `ProbeCache`（`self._store: dict[str, tuple[ProbeReport, float]]`、`self._lock`）。
- Produces: `ProbeCache.stats() -> dict`：`{entries:int, expired:int}`。

- [ ] **Step 1: 写失败测试**

在 `tests/llm/test_probe_cache.py` 追加（沿用既有 `autouse` reset fixture 与 monotonic monkeypatch 范式）：

```python
def test_stats_counts_entries_and_expired(get_probe_cache_fixture):
    c = ProbeCache(default_ttl_seconds=86400.0)
    c.put("k1", _sample_report(), ttl_seconds=100)
    c.put("k2", _sample_report(), ttl_seconds=-1)  # 立即过期
    s = c.stats()
    assert s["entries"] == 2
    assert s["expired"] == 1
```

（`_sample_report` 用本文件既有样例，或新建最小 ProbeReport 构造。）

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/llm/test_probe_cache.py -k stats -v`
Expected: FAIL（无 `stats` 属性）

- [ ] **Step 3: 最小实现**

在 `ProbeCache` 加：

```python
def stats(self) -> dict:
    """能力探测缓存统计（进程内）。"""
    with self._lock:
        now = time.monotonic()
        expired = sum(1 for _, expiry in self._store.values() if now >= expiry)
        return {"entries": len(self._store), "expired": expired}
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/llm/test_probe_cache.py -k stats -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/llm/test_probe_cache.py src/finance_agent/llm/probe_cache.py
git commit -m "feat(probe-cache): 能力探测缓存统计"
```

---

### Task 5: session_store 清空全部会话

**Files:**
- Modify: `src/finance_agent/session_store.py`
- Test: `tests/test_session_store.py`

**Interfaces:**
- Consumes: `_get_db()`、表 `sessions`/`session_events`。
- Produces: `clear_all_sessions() -> int`（删除的会话数）。

- [ ] **Step 1: 写失败测试**

在 `tests/test_session_store.py` 追加（沿用 `monkeypatch.setattr(session_store, "_DB_PATH", ...)` + `init_db()` 范式）：

```python
def test_clear_all_sessions_cascades_events(tmp_path, monkeypatch):
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "s.db")
    session_store.init_db()
    # 建两个会话 + 事件（沿用本文件既有建会话 helper）
    ...
    n = session_store.clear_all_sessions()
    assert n == 2
    assert session_store.list_sessions() == []
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_session_store.py -k clear_all -v`
Expected: FAIL（无 `clear_all_sessions`）

- [ ] **Step 3: 最小实现**

在 `session_store.py`（`delete_session` 之后）加：

```python
def clear_all_sessions() -> int:
    """清空全部会话及其事件日志，返回删除的会话数。"""
    conn = _get_db()
    try:
        n = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.execute("DELETE FROM session_events")
        conn.execute("DELETE FROM sessions")
        conn.commit()
        return n
    finally:
        conn.close()
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_session_store.py -k clear_all -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/test_session_store.py src/finance_agent/session_store.py
git commit -m "feat(session): 清空全部会话（级联删事件）"
```

---

### Task 6: API 端点（cache / clear-all / run-info / data-source）

**Files:**
- Modify: `src/finance_agent/api.py`
- Test: `tests/test_api_settings.py`（新建）

**Interfaces:**
- Consumes: `get_shared_cache()`、`get_probe_cache()`、`get_monitor()`、`clear_all_sessions()`、`importlib.metadata`、`subprocess`。
- Produces（全部新增端点）:
  - `GET /api/cache/stats` → `{data, probe, monitor}`
  - `POST /api/cache/clear`（body `{scope: 'type'|'code'|'all', data_type?, code?, confirm?}`）→ `{scope, removed, ...}`；`scope=all` 无 `confirm=true` 时 400
  - `POST /api/cache/probe-cache/clear` → `{cleared: true}`
  - `POST /api/sessions/clear-all` → `{cleared: int}`
  - `GET /api/run-info` → 只读，绝不含 apiKey
  - `GET /api/data-source/status` → `{monitor, freshness}`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_api_settings.py`（仿 `tests/test_api_feedback.py` 的 `TestClient(app)` 形态）：

```python
from fastapi.testclient import TestClient
from finance_agent.api import app


def test_cache_stats_and_clear_all_requires_confirm():
    client = TestClient(app)
    # 造一个条目
    from finance_agent.data.cache import get_shared_cache
    get_shared_cache().set("600519:news", {"n": 1})
    s = client.get("/api/cache/stats").json()
    assert s["data"]["entries"] >= 1
    # 全清不带 confirm → 400
    assert client.post("/api/cache/clear", json={"scope": "all"}).status_code == 400
    # 带 confirm → 成功且清空
    r = client.post("/api/cache/clear", json={"scope": "all", "confirm": True})
    assert r.status_code == 200
    assert get_shared_cache().keys() == []


def test_run_info_never_exposes_api_key():
    client = TestClient(app)
    body = client.get("/api/run-info").json()
    assert "apiKey" not in body
    assert "api_key" not in body
    assert "model" in body and "base_url" in body


def test_data_source_status_shape():
    client = TestClient(app)
    body = client.get("/api/data-source/status").json()
    assert "monitor" in body and "freshness" in body


def test_sessions_clear_all_and_probe_clear():
    client = TestClient(app)
    assert client.post("/api/sessions/clear-all").status_code == 200
    assert client.post("/api/cache/probe-cache/clear").status_code == 200
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_api_settings.py -v`
Expected: FAIL（404，端点不存在）

- [ ] **Step 3: 最小实现**

在 `api.py` 顶部 import 区加（`import` 本身无副作用，getter 惰性创建）：

```python
from finance_agent.data.cache import get_shared_cache
from finance_agent.data.monitoring import get_monitor
from finance_agent.llm.probe_cache import get_probe_cache
from finance_agent.session_store import clear_all_sessions
```

请求模型（放在其它 `XxxRequest` 旁）：

```python
class CacheClearRequest(BaseModel):
    scope: str  # type | code | all
    data_type: str | None = None
    code: str | None = None
    confirm: bool = False
```

端点（追加在既有端点之后，仿 `GET /api/decisions/stats` 的 `await asyncio.to_thread(...)` 范式）：

```python
@app.get("/api/cache/stats")
async def cache_stats() -> dict:
    data = await asyncio.to_thread(get_shared_cache().stats)
    probe = await asyncio.to_thread(get_probe_cache().stats)
    return {"data": data, "probe": probe, "monitor": get_monitor().snapshot()}


@app.post("/api/cache/clear")
async def cache_clear(req: CacheClearRequest) -> dict:
    cache = get_shared_cache()
    if req.scope == "all":
        if not req.confirm:
            raise HTTPException(status_code=400, detail="clear all requires confirm=true")
        removed = await asyncio.to_thread(cache.clear_all)
        return {"scope": "all", "removed": removed}
    if req.scope == "type":
        if not req.data_type:
            raise HTTPException(status_code=400, detail="data_type required for scope=type")
        removed = await asyncio.to_thread(cache.delete_by_type, req.data_type)
        return {"scope": "type", "data_type": req.data_type, "removed": removed}
    if req.scope == "code":
        if not req.code:
            raise HTTPException(status_code=400, detail="code required for scope=code")
        removed = await asyncio.to_thread(cache.delete_by_code, req.code)
        return {"scope": "code", "code": req.code, "removed": removed}
    raise HTTPException(status_code=400, detail="unknown scope")


@app.post("/api/cache/probe-cache/clear")
async def probe_cache_clear() -> dict:
    await asyncio.to_thread(get_probe_cache().clear)
    return {"cleared": True}


@app.post("/api/sessions/clear-all")
async def clear_all_sessions_endpoint() -> dict:
    n = await asyncio.to_thread(clear_all_sessions)
    return {"cleared": n}
```

run-info 辅助与端点（顶部 `import functools, importlib.metadata, subprocess`，`Path` 已有）：

```python
@functools.lru_cache(maxsize=1)
def _git_commit() -> str | None:
    root = Path(__file__).resolve().parents[3]
    if (root / ".git").exists():
        try:
            out = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=2)
            if out.returncode == 0:
                return out.stdout.strip()[:12]
        except Exception:
            return None
    return None


@app.get("/api/run-info")
async def run_info() -> dict:
    model = os.environ.get("LLM_MODEL") or "deepseek/deepseek-chat"
    base_url = os.environ.get("LLM_BASE_URL") or ""
    thinking = os.environ.get("LLM_THINKING") or "enabled"
    langfuse_host = os.environ.get("LANGFUSE_HOST") or "http://localhost:3000"
    langfuse_enabled = bool(os.environ.get("LANGFUSE_PUBLIC_KEY")
                            and os.environ.get("LANGFUSE_SECRET_KEY"))
    version = "0.1.0"
    try:
        version = importlib.metadata.version("finance-agent")
    except Exception:
        pass
    return {
        "model": model, "base_url": base_url, "thinking": thinking,
        "langfuse_host": langfuse_host, "langfuse_enabled": langfuse_enabled,
        "version": version, "git_commit": _git_commit(), "health": "ok",
    }


@app.get("/api/data-source/status")
async def data_source_status() -> dict:
    data = await asyncio.to_thread(get_shared_cache().stats)
    return {"monitor": get_monitor().snapshot(), "freshness": data}
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_api_settings.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/test_api_settings.py src/finance_agent/api.py
git commit -m "feat(api): 缓存统计/清理、会话清空、run-info、数据源状态端点"
```

---

### Task 7: 抽 LlmConfigPane 复用组件 + 设置中心页壳与路由

**Files:**
- Create: `frontend/src/pages/settings/SettingsCenterPage.tsx`
- Create: `frontend/src/pages/settings/panes/LlmConfigPane.tsx`
- Modify: `frontend/src/App.tsx`（路由分支 `:894` 后加 `/settings`；侧栏 gear `:1177-1181`、header 设置 `:951-953`、EmptyState「去配置/修改」`1541/1547`、强制配置三处 `578/1404/1413/1490/2319/2326/2400` 改跳转；删除 `SettingsModal` 渲染 `1065-1079` 与定义 `2468`）
- Test: `frontend/src/test/settings/settingsCenterPage.test.tsx`（新建）

**Interfaces:**
- Consumes: `App.tsx` 现有 `config/backendDefaults/profileStore/capability/onProbeCapability/handleSaveConfig/handleSaveAsConfig/handleDeleteProfile/switchProfile`（`App.tsx:156-218`），`navigate`（`route.ts`）。
- Produces:
  - `LlmConfigPane` props = `SettingsModal` 的 props 去掉 `open`（`config, backendDefaults, profileStore, capability, onProbeCapability, onSave, onSaveAs, onSwitchProfile, onDeleteProfile`）。
  - `SettingsCenterPage({ config, backendDefaults, profileStore, capability, onProbeCapability, onSave, onSaveAs, onSwitchProfile, onDeleteProfile, onBack, initialModule?: ModuleId })`；`ModuleId = 'llm'|'cache'|'sessions'|'run'|'monitor'|'track'`。

- [ ] **Step 1: 写失败测试**

创建 `frontend/src/test/settings/settingsCenterPage.test.tsx`：

```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { SettingsCenterPage } from '../../pages/settings/SettingsCenterPage'
import { emptyLlmConfig } from '../../llmConfig'


const baseProps = {
  config: emptyLlmConfig(),
  backendDefaults: { model: 'deepseek/deepseek-chat', baseUrl: '', thinking: 'enabled' },
  profileStore: { profiles: [], activeId: '' },
  capability: null,
  onProbeCapability: vi.fn(),
  onSave: vi.fn(),
  onSaveAs: vi.fn(),
  onSwitchProfile: vi.fn(),
  onDeleteProfile: vi.fn(),
  onBack: vi.fn(),
}

describe('SettingsCenterPage', () => {
  it('默认激活 LLM 配置分区并显示其内容', () => {
    render(<SettingsCenterPage {...baseProps} />)
    // 左侧导航含六大分区
    expect(screen.getByText('缓存管理')).toBeInTheDocument()
    expect(screen.getByText('会话管理')).toBeInTheDocument()
    expect(screen.getByText('运行信息')).toBeInTheDocument()
    expect(screen.getByText('数据监控')).toBeInTheDocument()
    expect(screen.getByText('战绩展示偏好')).toBeInTheDocument()
  })

  it('点击左侧导航切换右侧内容区', () => {
    render(<SettingsCenterPage {...baseProps} />)
    fireEvent.click(screen.getByText('缓存管理'))
    expect(screen.getByText(/缓存管理/)).toBeInTheDocument()
  })

  it('initialModule=llm 时定位到 LLM 配置分区', () => {
    render(<SettingsCenterPage {...baseProps} initialModule="llm" />)
    // 出现 LLM 配置表单字段（如 Provider 预设）
    expect(screen.getByText(/Provider/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/test/settings/settingsCenterPage.test.tsx`
Expected: FAIL（组件不存在）

- [ ] **Step 3: 最小实现**

3a. 从 `App.tsx` 的 `SettingsModal`（`2468-2938`）抽出主体逻辑（内部编辑态 state、provider 预设、模型发现、连通性测试、profile 管理 JSX），去掉 `open` prop 与外层 Dialog 壳，导出为 `frontend/src/pages/settings/panes/LlmConfigPane.tsx`（props 同 `SettingsModal` 减 `open`；`App.tsx` 与设置页共用）。同步在 `App.tsx` 删除原 `SettingsModal` 定义。

3b. 创建 `SettingsCenterPage.tsx`：

```tsx
import { useState } from 'react'
import { LlmConfigPane } from './panes/LlmConfigPane'
import { CachePane } from './panes/CachePane'
import { SessionsPane } from './panes/SessionsPane'
import { RunInfoPane } from './panes/RunInfoPane'
import { DataMonitorPane } from './panes/DataMonitorPane'
import { TrackPrefsPane } from './panes/TrackPrefsPane'
import type { LLMConfig, CapabilityMatrix, ProfileStore } from '../../llmConfig'

export type ModuleId = 'llm' | 'cache' | 'sessions' | 'run' | 'monitor' | 'track'

const MODULES: { id: ModuleId; label: string }[] = [
  { id: 'llm', label: 'LLM 配置' },
  { id: 'cache', label: '缓存管理' },
  { id: 'sessions', label: '会话管理' },
  { id: 'run', label: '运行信息' },
  { id: 'monitor', label: '数据监控' },
  { id: 'track', label: '战绩展示偏好' },
]

export function SettingsCenterPage(props: {
  config: LLMConfig
  backendDefaults: { model: string; baseUrl: string; thinking: string }
  profileStore: ProfileStore
  capability: CapabilityMatrix | null
  onProbeCapability: (cap: CapabilityMatrix | null) => void
  onSave: (cfg: LLMConfig) => void
  onSaveAs: (cfg: LLMConfig, name: string) => void
  onSwitchProfile: (id: string) => void
  onDeleteProfile: (id: string) => void
  onBack: () => void
  initialModule?: ModuleId
}) {
  const [active, setActive] = useState<ModuleId>(props.initialModule ?? 'llm')
  return (
    <div data-testid="settings-center" style={{ display: 'flex', minHeight: '100vh' }}>
      <aside style={{ width: 180, background: 'var(--bg-overlay-l1)', borderRight: '1px solid var(--border-neutral-l1)', padding: 12 }}>
        <div style={{ fontWeight: 700, marginBottom: 12 }}>⚙ 设置</div>
        {MODULES.map((m) => (
          <button
            key={m.id}
            data-testid={`settings-nav-${m.id}`}
            onClick={() => setActive(m.id)}
            style={{
              display: 'block', width: '100%', textAlign: 'left', padding: '8px 10px', marginBottom: 4,
              borderRadius: 6, cursor: 'pointer', border: 'none',
              background: active === m.id ? 'var(--bg-brand)' : 'transparent',
              color: active === m.id ? 'var(--text-onbrand)' : 'var(--text-default)',
            }}
          >
            {m.label}
          </button>
        ))}
        <button data-testid="settings-back" onClick={props.onBack}
          style={{ marginTop: 12, ...按钮样式 }}>← 返回</button>
      </aside>
      <main style={{ flex: 1, padding: 20 }}>
        {active === 'llm' && <LlmConfigPane {...props} />}
        {active === 'cache' && <CachePane />}
        {active === 'sessions' && <SessionsPane onCleared={props.onBack} />}
        {active === 'run' && <RunInfoPane />}
        {active === 'monitor' && <DataMonitorPane />}
        {active === 'track' && <TrackPrefsPane />}
      </main>
    </div>
  )
}
```

3c. `App.tsx` 路由：在 `:894`（`/downloads`）之后插入：

```tsx
) : pathname === '/settings' ? (
  <SettingsCenterPage
    config={config} backendDefaults={backendDefaults} profileStore={profileStore}
    capability={capability} onProbeCapability={handleProbeCapability}
    onSave={handleSaveConfig} onSaveAs={handleSaveAsConfig}
    onSwitchProfile={switchProfile} onDeleteProfile={handleDeleteProfile}
    onBack={() => navigate('/')} initialModule={settingsFocus}
  />
) : bootRestoring && viewState === 'empty' ? (
```

`settingsFocus` 为 App 新 state（`useState<ModuleId | undefined>(undefined)`），强制配置/入口跳转时 `setSettingsFocus('llm'); navigate('/settings')`。

3d. 入口迁移：`App.tsx:874` `onOpenSettings={() => setShowSettings(true)}` → `onOpenSettings={() => { setSettingsFocus(undefined); navigate('/settings') }}`；`951-953` header 设置同改；`1541/1547`「去配置/修改」改 `navigate('/settings')`；强制配置各点 `setShowSettings(true)` 全部改为 `{ setSettingsFocus('llm'); navigate('/settings') }`；删除 `showSettings` 状态（`:219`）与 `SettingsModal` 渲染（`:1065-1079`）。

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/test/settings/settingsCenterPage.test.tsx src/test/settingsProfileSwitch.test.tsx`
Expected: PASS（后者在 LlmConfigPane 迁移后仍绿）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/pages/settings frontend/src/App.tsx frontend/src/test/settings
git commit -m "feat(settings): 设置中心页壳+路由+入口迁移+LlmConfigPane 抽取"
```

---

### Task 8: 缓存管理分区

**Files:**
- Create: `frontend/src/pages/settings/panes/CachePane.tsx`
- Test: `frontend/src/test/settings/cachePane.test.tsx`

**Interfaces:**
- Consumes: `GET /api/cache/stats`、`POST /api/cache/clear`、`POST /api/cache/probe-cache/clear`（Task 6）。
- Produces: `CachePane`（无 props）。

- [ ] **Step 1: 写失败测试**

```tsx
// cachePane.test.tsx —— stub fetch 按 URL 分发
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { CachePane } from '../../pages/settings/panes/CachePane'

const statsBody = {
  data: { entries: 3, bytes: 100, expired: 1, permanent: 1,
          per_type: [{ category: 'kline', entries: 2, bytes: 50, earliest_expire: 123 }] },
  probe: { entries: 0, expired: 0 },
  monitor: { hits: 1, misses: 0, fails: {}, last_hit: 123 },
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith('/api/cache/stats')) return Promise.resolve(new Response(JSON.stringify(statsBody)))
    return Promise.resolve(new Response(JSON.stringify({ ok: true })))
  }))
})

it('展示汇总统计与类别表格', async () => {
  render(<CachePane />)
  expect(await screen.findByText('3')).toBeInTheDocument()
  expect(screen.getByText('kline')).toBeInTheDocument()
})

it('按类别清空调用 /api/cache/clear', async () => {
  render(<CachePane />)
  fireEvent.click(await screen.findByText('清空该类'))
  await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/cache/clear', expect.any(Object)))
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/test/settings/cachePane.test.tsx`
Expected: FAIL

- [ ] **Step 3: 最小实现**

`CachePane.tsx`：挂载拉 `GET /api/cache/stats`，渲染汇总统计条（总条目/占用/已过期待清/最近命中）与类别表格（每类「清空该类」调 `POST /api/cache/clear {scope:'type', data_type}`）、按代码输入框调 `{scope:'code', code}`、全部清空按钮弹确认框（输入「清空」匹配后调 `{scope:'all', confirm:true}`）、能力探测缓存一键清除调 `/api/cache/probe-cache/clear`；每次操作后刷新 stats。用现有 `div.rounded-xl + var(--bg-overlay-l1)` 卡片风格与原生 `<select>/<input>`。

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/test/settings/cachePane.test.tsx`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add frontend/src/pages/settings/panes/CachePane.tsx frontend/src/test/settings/cachePane.test.tsx
git commit -m "feat(settings): 缓存管理分区"
```

---

### Task 9: 会话管理分区

**Files:**
- Create: `frontend/src/pages/settings/panes/SessionsPane.tsx`
- Test: `frontend/src/test/settings/sessionsPane.test.tsx`

**Interfaces:**
- Consumes: `GET /api/sessions`（会话数）、`POST /api/sessions/clear-all`（Task 6）。
- Produces: `SessionsPane({ onCleared }: { onCleared?: () => void })`。

- [ ] **Step 1: 写失败测试**

```tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { SessionsPane } from '../../pages/settings/panes/SessionsPane'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    if (url.endsWith('/api/sessions')) return Promise.resolve(new Response(JSON.stringify([{}, {}, {}])))
    if (url.endsWith('/api/sessions/clear-all')) return Promise.resolve(new Response(JSON.stringify({ cleared: 3 })))
    return Promise.resolve(new Response('{}'))
  }))
})

it('展示会话总数并二次确认后清空', async () => {
  const onCleared = vi.fn()
  render(<SessionsPane onCleared={onCleared} />)
  expect(await screen.findByText('3')).toBeInTheDocument()
  fireEvent.click(screen.getByText('清空全部会话'))
  expect(screen.getByText(/确认/)).toBeInTheDocument()
  fireEvent.click(screen.getByText('确认清空'))
  await waitFor(() => expect(onCleared).toHaveBeenCalled())
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/test/settings/sessionsPane.test.tsx`
Expected: FAIL

- [ ] **Step 3: 最小实现**

`SessionsPane.tsx`：挂载拉 `GET /api/sessions` 显示 `sessions.length`；「清空全部会话」弹二次确认框，确认后 `POST /api/sessions/clear-all` 并回调 `onCleared`。

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/test/settings/sessionsPane.test.tsx`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add frontend/src/pages/settings/panes/SessionsPane.tsx frontend/src/test/settings/sessionsPane.test.tsx
git commit -m "feat(settings): 会话管理分区（清空全部）"
```

---

### Task 10: 运行信息分区

**Files:**
- Create: `frontend/src/pages/settings/panes/RunInfoPane.tsx`
- Test: `frontend/src/test/settings/runInfoPane.test.tsx`

**Interfaces:**
- Consumes: `GET /api/run-info`（Task 6）。
- Produces: `RunInfoPane`。

- [ ] **Step 1: 写失败测试**

```tsx
import { render, screen } from '@testing-library/react'
import { RunInfoPane } from '../../pages/settings/panes/RunInfoPane'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify({
    model: 'deepseek/deepseek-chat', base_url: 'https://api.deepseek.com/v1',
    thinking: 'enabled', langfuse_host: 'http://localhost:3000', langfuse_enabled: true,
    version: '0.1.0', git_commit: 'abc123', health: 'ok',
  })))))
})

it('只读展示后端运行信息', async () => {
  render(<RunInfoPane />)
  expect(await screen.findByText(/deepseek\/deepseek-chat/)).toBeInTheDocument()
  expect(screen.getByText(/abc123/)).toBeInTheDocument()
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/test/settings/runInfoPane.test.tsx`
Expected: FAIL

- [ ] **Step 3: 最小实现**

`RunInfoPane.tsx`：挂载拉 `GET /api/run-info`，只读展示 model/base_url/thinking/健康/版本/git commit/Langfuse 地址与启用态；不渲染任何密钥字段。

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/test/settings/runInfoPane.test.tsx`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add frontend/src/pages/settings/panes/RunInfoPane.tsx frontend/src/test/settings/runInfoPane.test.tsx
git commit -m "feat(settings): 运行信息分区"
```

---

### Task 11: 数据监控分区

**Files:**
- Create: `frontend/src/pages/settings/panes/DataMonitorPane.tsx`
- Test: `frontend/src/test/settings/dataMonitorPane.test.tsx`

**Interfaces:**
- Consumes: `GET /api/data-source/status`（Task 6）。
- Produces: `DataMonitorPane`。

- [ ] **Step 1: 写失败测试**

```tsx
import { render, screen } from '@testing-library/react'
import { DataMonitorPane } from '../../pages/settings/panes/DataMonitorPane'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify({
    monitor: { hits: 5, misses: 2, fails: { kline: 1 }, last_hit: null },
    freshness: { entries: 3, per_type: [{ category: 'kline', entries: 2, earliest_expire: null }] },
  })))))
})

it('展示命中/未命中/失败计数与新鲜度', async () => {
  render(<DataMonitorPane />)
  expect(await screen.findByText('5')).toBeInTheDocument()
  expect(screen.getByText('2')).toBeInTheDocument()
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/test/settings/dataMonitorPane.test.tsx`
Expected: FAIL

- [ ] **Step 3: 最小实现**

`DataMonitorPane.tsx`：挂载拉 `GET /api/data-source/status`，渲染命中/未命中/失败计数卡 + 数据新鲜度列表（含已过期标记）；含加载/错误态。

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/test/settings/dataMonitorPane.test.tsx`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add frontend/src/pages/settings/panes/DataMonitorPane.tsx frontend/src/test/settings/dataMonitorPane.test.tsx
git commit -m "feat(settings): 数据监控分区"
```

---

### Task 12: 战绩展示偏好（localStorage + 分区 + 战绩页消费）

**Files:**
- Create: `frontend/src/lib/trackPrefs.ts`
- Create: `frontend/src/pages/settings/panes/TrackPrefsPane.tsx`
- Modify: `frontend/src/pages/trackRecord/TrackRecordPage.tsx`（时间跨度 `:90`、基准 `:166-176`、回撤阈值 `:269`、净值图形态 `:173-174`）
- Test: `frontend/src/test/settings/trackPrefsPane.test.tsx`、`frontend/src/test/trackRecord/trackRecordPage.test.tsx`

**Interfaces:**
- Consumes: 无后端；纯 localStorage。
- Produces:
  - `TrackPrefs { timeSpan: string; benchmark: string; drawdownThreshold: number; navChartForm: string }`
  - `loadTrackPrefs() -> TrackPrefs`、`saveTrackPrefs(p: TrackPrefs) -> void`、`DEFAULT_TRACK_PREFS`（key `fa_track_prefs`）。

- [ ] **Step 1: 写失败测试**

```ts
// trackPrefs.ts 单测
import { loadTrackPrefs, saveTrackPrefs, DEFAULT_TRACK_PREFS } from '../../lib/trackPrefs'

it('默认值与持久化', () => {
  expect(loadTrackPrefs()).toEqual(DEFAULT_TRACK_PREFS)
  saveTrackPrefs({ ...DEFAULT_TRACK_PREFS, timeSpan: '6m' })
  expect(loadTrackPrefs().timeSpan).toBe('6m')
  localStorage.clear()
})
```

`TrackRecordPage` 消费测试：在 `trackRecordPage.test.tsx` 追加——`beforeEach` 设 `localStorage.fa_track_prefs = JSON.stringify({ timeSpan:'6m', benchmark:'中证500', drawdownThreshold:0.1, navChartForm:'area' })`，断言请求 URL 含跨度参数、回撤警示用 0.1 阈值、净值 series 面积形态。

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/test/settings/trackPrefsPane.test.tsx src/test/trackRecord/trackRecordPage.test.tsx`
Expected: FAIL

- [ ] **Step 3: 最小实现**

3a. `trackPrefs.ts`：

```ts
export interface TrackPrefs {
  timeSpan: string      // 'all' | '3m' | '6m' | '1y'
  benchmark: string     // 'none' | 'hs300' | 'zz500' | 'zz1000'
  drawdownThreshold: number
  navChartForm: string  // 'cumulative' | 'interval'
}
export const DEFAULT_TRACK_PREFS: TrackPrefs = {
  timeSpan: 'all', benchmark: 'none', drawdownThreshold: 0.2, navChartForm: 'cumulative',
}
const KEY = 'fa_track_prefs'
export function loadTrackPrefs(): TrackPrefs {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? { ...DEFAULT_TRACK_PREFS, ...JSON.parse(raw) } : { ...DEFAULT_TRACK_PREFS }
  } catch { return { ...DEFAULT_TRACK_PREFS } }
}
export function saveTrackPrefs(p: TrackPrefs): void {
  localStorage.setItem(KEY, JSON.stringify(p))
}
```

3b. `TrackPrefsPane.tsx`：四项偏好（时间跨度/基准/回撤阈值/净值图形态），读写 `loadTrackPrefs/saveTrackPrefs`，改动即保存。

3c. `TrackRecordPage.tsx` 消费：`load()` 请求 equity-curve 时按 `timeSpan` 附加区间参数（后端若暂不支持则前端过滤数据）；`:173-174` series 数组按 `benchmark` 决定是否叠加基准线、按 `navChartForm` 决定 `type:'line'` 或 `'line'+areaStyle`；`:269` 的 `0.2` 改为 `loadTrackPrefs().drawdownThreshold`。基准项若后端无对应基准序列，按 `benchmark==='none'` 只渲染组合净值，其余值保持现状（标注待确认）。

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/test/settings/trackPrefsPane.test.tsx src/test/trackRecord/trackRecordPage.test.tsx`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add frontend/src/lib/trackPrefs.ts frontend/src/pages/settings/panes/TrackPrefsPane.tsx \
  frontend/src/pages/trackRecord/TrackRecordPage.tsx frontend/src/test
git commit -m "feat(settings): 战绩展示偏好存储与战绩页消费"
```

---

### Task 13: LLM 切换下拉框「LLM 配置…」分隔项

**Files:**
- Modify: `frontend/src/App.tsx`（EmptyState 下拉 `:1500-1513`、ChatInputBar 下拉 `:2410-2423`）
- Test: `frontend/src/test/dropdownOutsideClick.test.tsx`（追加用例）

**Interfaces:**
- Consumes: `onOpenSettings`（已由 Task 7 改为 `navigate('/settings')`）。
- Produces: 无新签名。

- [ ] **Step 1: 写失败测试**

在 `dropdownOutsideClick.test.tsx` 追加：

```tsx
it('LLM 下拉底部以分隔线展示 LLM 配置项且点击跳转设置页', () => {
  const onOpenSettings = vi.fn()
  render(<EmptyState {...props} onOpenSettings={onOpenSettings} profiles={[p1]} />)
  fireEvent.click(screen.getByRole('button', { name: 'LLM' }))  // 触发按钮按实际名称
  const item = screen.getByRole('button', { name: 'LLM 配置…' })
  fireEvent.click(item)
  expect(onOpenSettings).toHaveBeenCalled()
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/test/dropdownOutsideClick.test.tsx`
Expected: FAIL（无「LLM 配置…」项）

- [ ] **Step 3: 最小实现**

EmptyState 与 ChatInputBar 的下拉列表（profile map 之后）追加分隔线与项：

```tsx
{profiles.length > 0 && (
  <div style={{ borderTop: '1px solid var(--border-neutral-l1)', margin: '4px 0' }} />
)}
<button onClick={() => { setLlmDropdownOpen(false); onOpenSettings() }} style={...}>
  LLM 配置…
</button>
```

此分隔项不调用 `onSwitchProfile`，不改变激活 profile。

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/test/dropdownOutsideClick.test.tsx`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add frontend/src/App.tsx frontend/src/test/dropdownOutsideClick.test.tsx
git commit -m "feat(settings): LLM 下拉框 LLM 配置分隔项"
```

---

### Task 14: 全量验证与 E2E

**Files:**
- E2E（若基础设施就绪）: `e2e/tests/settings.spec.ts`（新建）
- Test: `tests/validation/`（人工验证报告，实施后补）

**Interfaces:**
- Consumes: 全部上述任务产物。

- [ ] **Step 1: 后端全量回归**

Run: `uv run pytest`
Expected: PASS（0 failures）

- [ ] **Step 2: 前端全量测试与构建**

Run: `cd frontend && npx vitest run && npm run build`
Expected: PASS，build 无类型错误

- [ ] **Step 3: E2E 门禁**

Run: `cd e2e && npx playwright test`
若 e2e/ 基础设施未落地（P1–P4 未完成），按 project-workflow §3 Step 4.5 豁免，在人工验证报告中记录；否则写 `settings.spec.ts` 覆盖：设置页可达、左侧导航切换、缓存全清确认交互、无 profile 强制配置引导跳转设置页。

- [ ] **Step 4: Lint / 类型**

Run: `uv run ruff check && uv run mypy`
Expected: PASS

- [ ] **Step 5: 提交 + 人工验证报告**

```bash
git add -A
git commit -m "chore(settings): 全量验证与 E2E"
```

补 `tests/validation/2026-09-08-add-agent-settings-center-validation.md`（含设置页各分区截图证据；基准对比项接入状态如实记录）。
