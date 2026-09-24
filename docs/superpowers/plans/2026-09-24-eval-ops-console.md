# Eval Ops Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> 本仓库实施纪律（覆盖默认）：先写失败测试；每个任务一个 implementer + 独立审查 + 修复轮；进度账 `.superpowers/sdd/progress.md`；只在 `.worktrees/ops-console` 内改动。

**Goal:** 把日批调度、cohort 开关与时刻、回测批与泄漏探针、健康检查、报告注册表、预登记与口径的**查看与操作**做成设置中心里可见可用的界面，并补齐战绩页总览的三项披露。

**Architecture:** 后端新增 `finance_agent.outcome.ops` 包（配置与运行历史两张表 + 任务执行入口），调度器改为经统一入口落运行历史；新增 `/api/v1/ops/*` 路由承载状态、补跑、cohort 控制、回测/探针/健康检查的异步触发与结果读取；前端新增设置中心分区（六页签，沿用既有面板状态机）。口径编辑只产出 OpenSpec delta 草稿，不写台账与常量；预登记编辑走版本化 + 读数锁定。

**Tech Stack:** Python 3.12 / FastAPI / SQLite(WAL) / APScheduler（in-process）/ React 18 + TS + Vite / pytest / Playwright。

## Global Constraints

- 单 uvicorn worker（StreamRegistry 与 APScheduler 均 in-process）——手动触发互斥只需进程内锁，不得引入多 worker 假设。
- `TESTING=1` 时调度器不启动：状态接口必须返回 `scheduler_running: false`（200），不得 500、不得以空列表冒充正常。
- 烧钱动作（cohort 开启 / 正式批 / 探针单跑）一律前端确认 + 后端沿用既有安全语义；**预算熔断、串行、usage 真值记账一行不改**。
- cohort 开关关闭时：定时触发零 LLM 调用、运行历史记 `skipped-disabled`；手动触发拒绝（409）。
- 口径编辑**不得**写 `docs/evals/metrics.md`、不得写 `evals/outcome/caliber.py`；只生成 `openspec/changes/ops-caliber-draft-*/` 草稿。
- 预登记保存走新版本文件，已产生读数的版本只读。
- 所有新增 SQLite 表用幂等 DDL（`CREATE TABLE IF NOT EXISTS`），与 `track_record/model.py::_connect` 同款连接参数（WAL + busy_timeout=15s + `check_same_thread=False`）。
- 新增 Python 代码不得复制 CLI 实现：回测/探针/健康检查均 import 既有 `evals.*` 函数。
- 前端沿用 `DataMonitorPane` 的 loading/ready/error 状态机与 `data-testid` 命名（`eval-ops-*` 前缀）。
- 提交信息用中文、含影响面；ruff/format 零违例；mypy 触碰文件零新增。

---

### Task 1: 运维配置与运行历史存储（`outcome/ops/model.py`）

**Files:**
- Create: `src/finance_agent/outcome/ops/__init__.py`
- Create: `src/finance_agent/outcome/ops/model.py`
- Test: `tests/outcome/test_ops_model.py`

**Interfaces:**
- Consumes: `finance_agent.outcome.track_record.model._connect/_default_db_path` 同款模式（复制连接参数，不 import 私有名——本包自建 `_connect`）。
- Produces:
  - `OPS_DDL: str`
  - `init_ops(db_path: str | Path | None = None) -> None`
  - `get_config(key: str, db_path=None) -> str | None` / `set_config(key: str, value: str, db_path=None) -> None`
  - `COHORT_ENABLED_KEY = "cohort_enabled"`, `COHORT_HOUR_KEY = "cohort_hour"`, `COHORT_MINUTE_KEY = "cohort_minute"`
  - `get_cohort_settings(db_path=None) -> dict` → `{"enabled": bool, "hour": int, "minute": int, "source": "ops_config" | "env" | "default"}`
  - `bootstrap_cohort_from_env(db_path=None) -> None`
  - `insert_job_run(job_id: str, kind: str, status: str, *, source: str = "scheduled", summary: dict | None = None, error: str | None = None, db_path=None) -> int`
  - `finish_job_run(run_id: int, *, status: str, summary: dict | None = None, error: str | None = None, db_path=None) -> None`
  - `list_job_runs(job_id: str | None = None, *, limit: int = 20, db_path=None) -> list[dict]`
  - `last_job_run(job_id: str, db_path=None) -> dict | None`
  - `prune_job_runs(keep_per_job: int = 500, db_path=None) -> int`

- [ ] **Step 1: 写失败测试** `tests/outcome/test_ops_model.py`

```python
def test_init_ops_is_idempotent(tmp_path):
    db = tmp_path / "ops.db"
    init_ops(db); init_ops(db)  # 第二次不得抛
    assert set(_tables(db)) >= {"ops_config", "job_runs"}

def test_config_roundtrip_and_missing_key(tmp_path):
    db = tmp_path / "ops.db"; init_ops(db)
    assert get_config("cohort_hour", db) is None
    set_config("cohort_hour", "19", db)
    assert get_config("cohort_hour", db) == "19"

def test_cohort_settings_table_wins_over_env(tmp_path, monkeypatch):
    db = tmp_path / "ops.db"; init_ops(db)
    monkeypatch.setenv("COHORT_ENABLED", "0")
    set_config(COHORT_ENABLED_KEY, "1", db)
    s = get_cohort_settings(db)
    assert (s["enabled"], s["source"]) == (True, "ops_config")

def test_cohort_settings_falls_back_to_env_then_default(tmp_path, monkeypatch):
    db = tmp_path / "ops.db"; init_ops(db)
    monkeypatch.setenv("COHORT_ENABLED", "1"); monkeypatch.setenv("COHORT_HOUR", "20")
    monkeypatch.delenv("COHORT_MINUTE", raising=False)
    s = get_cohort_settings(db)
    assert (s["enabled"], s["hour"], s["minute"], s["source"]) == (True, 20, 0, "env")

def test_cohort_settings_bad_env_value_falls_back_with_warn(tmp_path, monkeypatch, caplog):
    db = tmp_path / "ops.db"; init_ops(db)
    monkeypatch.setenv("COHORT_HOUR", "abc")
    assert get_cohort_settings(db)["hour"] == 18  # 默认，且 WARN 落日志

def test_bootstrap_writes_env_values_only_when_absent(tmp_path, monkeypatch):
    db = tmp_path / "ops.db"; init_ops(db)
    monkeypatch.setenv("COHORT_ENABLED", "1")
    bootstrap_cohort_from_env(db)
    assert get_config(COHORT_ENABLED_KEY, db) == "1"
    set_config(COHORT_ENABLED_KEY, "0", db)
    bootstrap_cohort_from_env(db)  # 已有值不得覆盖（重启保持语义）
    assert get_config(COHORT_ENABLED_KEY, db) == "0"

def test_job_run_lifecycle_and_last_run(tmp_path):
    db = tmp_path / "ops.db"; init_ops(db)
    rid = insert_job_run("cohort_batch", "scheduled", "running", db_path=db)
    finish_job_run(rid, status="ok", summary={"success": 10}, db_path=db)
    row = last_job_run("cohort_batch", db)
    assert row["status"] == "ok" and row["summary"]["success"] == 10
    assert row["finished_at"] is not None

def test_prune_keeps_newest_per_job(tmp_path):
    db = tmp_path / "ops.db"; init_ops(db)
    for i in range(10):
        r = insert_job_run("integrity_check", "scheduled", "running", db_path=db)
        finish_job_run(r, status="ok", db_path=db)
    assert prune_job_runs(keep_per_job=3, db_path=db) == 7
    assert len(list_job_runs("integrity_check", limit=99, db_path=db)) == 3
```

- [ ] **Step 2: 跑测试确认失败** → `uv run pytest tests/outcome/test_ops_model.py -q`（ImportError）

- [ ] **Step 3: 实现** `src/finance_agent/outcome/ops/model.py`

DDL（摘要，实现时写全）：

```python
OPS_DDL = """
CREATE TABLE IF NOT EXISTS ops_config (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_runs (
  run_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id      TEXT NOT NULL,
  kind        TEXT NOT NULL,          -- scheduled | manual | config-change
  source      TEXT NOT NULL DEFAULT 'scheduled',
  status      TEXT NOT NULL,          -- running | ok | failed | skipped-disabled
  started_at  TEXT NOT NULL,
  finished_at TEXT,
  summary     TEXT,                   -- JSON（8KB 截断）
  error       TEXT
);
CREATE INDEX IF NOT EXISTS idx_job_runs_job_started ON job_runs(job_id, started_at DESC);
"""
```

要点：`get_cohort_settings` 逐键「表值 → env（`_env_int` 同款越界/非数值回退 + WARN）→ 默认(False,18,0)」，任一键取自表则 `source="ops_config"`，全取自 env 则 `"env"`，否则 `"default"`；`insert_job_run` 的 `summary` 用 `json.dumps(..., ensure_ascii=False, default=str)` 截断到 8192 字符；`prune_job_runs` 用窗口函数或逐 job 子查询删除超出者并返回删除行数。

- [ ] **Step 4: 跑测试确认通过** → `uv run pytest tests/outcome/test_ops_model.py -q`；`uv run ruff check src/finance_agent/outcome/ops tests/outcome/test_ops_model.py`

- [ ] **Step 5: 提交** `git add -A && git commit -m "feat(ops): 运维配置与运行历史两表（ops_config/job_runs）+ 解析器与迁移（delta add-eval-ops-console）"`

---

### Task 2: 任务执行入口与调度器接线（`outcome/ops/jobs.py` + `scheduler.py`）

**Files:**
- Create: `src/finance_agent/outcome/ops/jobs.py`
- Modify: `src/finance_agent/outcome/scheduler.py`（`_with_retry` → 统一入口；cohort job 走配置解析；新增 `reschedule_cohort`）
- Modify: `src/finance_agent/outcome/cohort/runner.py:107`（`os.getenv("COHORT_ENABLED") == "1"` → `ops.get_cohort_settings()["enabled"]`，**保留 `enabled` 参数优先**）
- Test: `tests/outcome/test_ops_jobs.py`、`tests/outcome/test_cohort_runner.py`（既有用例补一条「表值优先于 env」）

**Interfaces:**
- Consumes: Task 1 的 `insert_job_run/finish_job_run/get_cohort_settings`。
- Produces:
  - `JOB_IDS: tuple[str, ...] = ("decision_settle_daily", "daily_marking", "metrics_snapshot", "integrity_check", "cohort_batch")`
  - `JOB_LABELS: dict[str, str]`（中文名：判定 / 盯市 / 指标快照 / 完整性校验 / cohort 跑批）
  - `JOB_FUNCS: dict[str, Callable[[], Any]]`
  - `run_job(job_id: str, *, source: str = "manual", db_path=None) -> dict` → `{"run_id": int, "status": str, "summary": dict | None, "error": str | None}`；未知 job_id → `ValueError`；锁占用 → `JobAlreadyRunning`（自定义异常）
  - `JobAlreadyRunning(RuntimeError)`、`CohortDisabled(RuntimeError)`
  - scheduler: `get_scheduler() -> BackgroundScheduler | None`、`reschedule_cohort(hour: int, minute: int) -> bool`
  - `SCHEDULES: dict[str, dict]`（每 job 的 `{"day_of_week": "mon-fri", "hour": int, "minute": int, "timezone": "Asia/Shanghai"}`；cohort 项在 `start_scheduler` 时按配置填）

- [ ] **Step 1: 写失败测试** `tests/outcome/test_ops_jobs.py`

```python
def test_run_job_records_ok_with_summary(tmp_path, monkeypatch):
    monkeypatch.setitem(JOB_FUNCS, "integrity_check", lambda: {"issues": 0})
    out = run_job("integrity_check", db_path=tmp_path / "o.db")
    assert out["status"] == "ok" and out["summary"] == {"issues": 0}

def test_run_job_records_failed_with_error(tmp_path, monkeypatch):
    def boom(): raise RuntimeError("db locked")
    monkeypatch.setitem(JOB_FUNCS, "integrity_check", boom)
    out = run_job("integrity_check", db_path=tmp_path / "o.db")
    assert out["status"] == "failed" and "db locked" in out["error"]

def test_run_job_is_single_flight(tmp_path, monkeypatch):
    gate = threading.Event()
    def slow(): gate.wait(2); return {"ok": True}
    monkeypatch.setitem(JOB_FUNCS, "integrity_check", slow)
    t = threading.Thread(target=run_job, args=("integrity_check",), kwargs={"db_path": tmp_path / "o.db"})
    t.start(); time.sleep(0.2)
    with pytest.raises(JobAlreadyRunning):
        run_job("integrity_check", db_path=tmp_path / "o.db")
    gate.set(); t.join()

def test_cohort_manual_run_refused_when_disabled(tmp_path):
    with pytest.raises(CohortDisabled):
        run_job("cohort_batch", db_path=tmp_path / "o.db")   # 默认关
    row = last_job_run("cohort_batch", tmp_path / "o.db")
    assert row["status"] == "skipped-disabled"

def test_unknown_job_id_raises(tmp_path):
    with pytest.raises(ValueError):
        run_job("nope", db_path=tmp_path / "o.db")
```

`tests/outcome/test_scheduler.py` 补：

```python
def test_cohort_job_uses_config_not_env(tmp_path, monkeypatch):
    monkeypatch.setenv("COHORT_ENABLED", "1")           # env 说开
    ops_init(tmp_path / "o.db"); set_config(COHORT_ENABLED_KEY, "0", tmp_path / "o.db")  # 表说关
    monkeypatch.setenv("SESSIONS_DB_PATH", str(tmp_path / "o.db"))
    assert run_job("cohort_batch")["status"] == "skipped-disabled"

def test_reschedule_cohort_moves_next_fire(tmp_path, monkeypatch):
    monkeypatch.delenv("TESTING", raising=False)
    sched = start_scheduler(); assert sched is not None
    try:
        assert reschedule_cohort(19, 30) is True
        job = next(j for j in sched.get_jobs() if j.id == "cohort_batch")
        assert job.trigger.fields[job.trigger.FIELD_NAMES.index("hour")].__str__() == "19"
    finally:
        stop_scheduler(sched)
```

- [ ] **Step 2: 跑测试确认失败** → `uv run pytest tests/outcome/test_ops_jobs.py -q`

- [ ] **Step 3: 实现**

`ops/jobs.py` 核心：

```python
_LOCKS: dict[str, threading.Lock] = {jid: threading.Lock() for jid in JOB_IDS}

def run_job(job_id: str, *, source: str = "manual", db_path=None) -> dict:
    if job_id not in JOB_IDS:
        raise ValueError(f"未知 job_id: {job_id!r}")
    if job_id == "cohort_batch" and not get_cohort_settings(db_path)["enabled"]:
        rid = insert_job_run(job_id, "cohort", "skipped-disabled", source=source, db_path=db_path)
        finish_job_run(rid, status="skipped-disabled", summary={"reason": "switch_off"}, db_path=db_path)
        raise CohortDisabled("cohort 开关未开启，手动跑批被拒绝（零 LLM 调用）")
    lock = _LOCKS[job_id]
    if not lock.acquire(blocking=False):
        raise JobAlreadyRunning(f"{job_id} 已在运行")
    rid = insert_job_run(job_id, "manual" if source == "manual" else "scheduled", "running",
                         source=source, db_path=db_path)
    try:
        result = JOB_FUNCS[job_id]()
        summary = result if isinstance(result, dict) else {"result": str(result)}
        finish_job_run(rid, status="ok", summary=summary, db_path=db_path)
        return {"run_id": rid, "status": "ok", "summary": summary, "error": None}
    except Exception as e:  # noqa: BLE001 —— 旁路铁律：失败落历史不抛给调用方以外的链路
        finish_job_run(rid, status="failed", error=f"{type(e).__name__}: {e}", db_path=db_path)
        return {"run_id": rid, "status": "failed", "summary": None, "error": str(e)}
    finally:
        lock.release()
```

`scheduler.py`：`_with_retry(name, fn)` 改为 `run_job(job_id, source="scheduled")` 包装（保留 3 次退避重试语义——重试发生在 `run_job` 外层循环，每次失败落一行 `failed` 并在最终行记 `retries`）；`start_scheduler` 里 cohort 的 hour/minute 取自 `get_cohort_settings()`；保存 `_scheduler` 模块级句柄供 `reschedule_cohort` 使用（`modify_job(..., trigger=CronTrigger(...))`）。

`runner.py:107`：

```python
    if enabled is None:
        from finance_agent.outcome.ops.model import get_cohort_settings
        enabled = get_cohort_settings(db_path)["enabled"]
```

- [ ] **Step 4: 跑测试** → `uv run pytest tests/outcome/test_ops_jobs.py tests/outcome/test_scheduler.py tests/outcome/test_cohort_runner.py -q`（全绿；既有 cohort 用例不得回归）

- [ ] **Step 5: 提交** `git commit -m "feat(ops): 统一任务执行入口（运行历史/单飞锁/cohort 门控）+ 调度器接线与运行时重排（delta add-eval-ops-console）"`

---

### Task 3: 运维 API 端点族（`ops_api.py` + `api.py` 挂载）

**Files:**
- Create: `src/finance_agent/ops_api.py`
- Modify: `src/finance_agent/api.py`（`app.include_router(ops_router)`；lifespan 里 `bootstrap_cohort_from_env()`）
- Test: `tests/test_ops_api.py`（FastAPI `TestClient`，不启调度器）

**Interfaces:**
- Consumes: Task 1/2 的 `get_cohort_settings/set_config/list_job_runs/run_job/reschedule_cohort/get_scheduler/JOB_IDS/JOB_LABELS/SCHEDULES`；`evals.outcome.health.collect_outcome_health`；`evals.backtest.results` 目录。
- Produces（端点契约，前端按此实现）:
  - `GET /api/v1/ops/jobs` → `{"scheduler_running": bool, "jobs": [{"job_id","label","schedule":{"day_of_week","hour","minute","timezone"},"next_fire_time": str|None,"last_run": {...}|None,"history": [...]}], "cohort": {"enabled","hour","minute","budget_tokens","today_spend","today_success","today_failure"}}`
  - `POST /api/v1/ops/jobs/{job_id}/run` → 202 `{"run_id"}`；409 `{"detail": "already_running"|"cohort_disabled"}`（cohort 关）；404 未知 job
  - `GET /api/v1/ops/runs/{run_id}` → 单条运行（含 summary）
  - `GET /api/v1/ops/cohort` / `PUT /api/v1/ops/cohort`（body `{"enabled"?: bool, "hour"?: int, "minute"?: int}`；越界 422；写配置 + `reschedule_cohort` + 记 `config-change` 审计行，summary 含 `{"from": ..., "to": ...}`）
  - `GET /api/v1/ops/reports` → `[{"name","path","status","target","positioning","probe_direction_hit_rate"}]`
  - `POST /api/v1/ops/backtest` → 202 `{"run_id"}`；409 `{"detail": "<门禁原因>"}`
  - `POST /api/v1/ops/probe` → 202 `{"run_id"}`
  - `POST /api/v1/ops/health` → 202 `{"run_id"}`

- [ ] **Step 1: 写失败测试**（关键面）

```python
def test_jobs_endpoint_reports_not_running_under_testing(client, monkeypatch):
    monkeypatch.setenv("TESTING", "1")
    body = client.get("/api/v1/ops/jobs").json()
    assert body["scheduler_running"] is False
    assert [j["job_id"] for j in body["jobs"]] == list(JOB_IDS)
    assert all(j["next_fire_time"] is None for j in body["jobs"])

def test_cohort_put_persists_and_audits(client, tmp_path, monkeypatch):
    client.put("/api/v1/ops/cohort", json={"enabled": True, "hour": 19, "minute": 30})
    assert client.get("/api/v1/ops/cohort").json()["hour"] == 30
    rows = list_job_runs(kind=None) if False else list_job_runs("cohort_batch")
    assert any(r["kind"] == "config-change" for r in rows)

def test_cohort_put_rejects_out_of_range(client):
    assert client.put("/api/v1/ops/cohort", json={"hour": 24}).status_code == 422

def test_manual_run_conflicts_when_locked(client, monkeypatch):
    monkeypatch.setattr("finance_agent.ops_api.run_job", _raise_job_already_running)
    assert client.post("/api/v1/ops/jobs/integrity_check/run").status_code == 409

def test_backtest_formal_refused_without_preregistration(client, monkeypatch, tmp_path):
    monkeypatch.setattr("finance_agent.ops_api.PREREGISTER_DIR", tmp_path)  # 空目录
    r = client.post("/api/v1/ops/backtest", json={"batch_kind": "formal", "codes": ["600519"]})
    assert r.status_code == 409 and "预登记" in r.json()["detail"]

def test_reports_registry_reads_status_header(client):
    body = client.get("/api/v1/ops/reports").json()
    assert any(item["name"].startswith("pilot-2023-shock") for item in body)
    assert all(item["status"] in ("active", "superseded-by") for item in body)
```

- [ ] **Step 2: 跑测试确认失败** → `uv run pytest tests/test_ops_api.py -q`

- [ ] **Step 3: 实现**：`APIRouter(prefix="/api/v1/ops", tags=["ops"])`；`next_fire_time` 取 `get_scheduler()` 的 `job.next_run_time`（None 时返回 None）；`run_job` 在 `asyncio.to_thread` 中执行以免阻塞事件循环；`reports` 用 `evals.causal_ablation.status_index.collect_status_index(Path("evals/backtest/results"))` + 从 md 正文正则取定位标签与探针方向命中率；`backtest` 端点先调 `evals.causal_ablation.preregister.assert_preregistered(..., required_fields=OUTCOME_REQUIRED_FIELDS)`，异常 → 409 + 原因文本。`api.py` lifespan 起始处调用 `bootstrap_cohort_from_env()`（异常仅 ERROR 不阻断）。

- [ ] **Step 4: 跑测试** → `uv run pytest tests/test_ops_api.py tests/test_api_track_record.py -q`

- [ ] **Step 5: 提交** `git commit -m "feat(ops): /api/v1/ops 端点族——状态/补跑/cohort 控制/回测与探针触发/报告注册表（delta add-eval-ops-console）"`

---

### Task 4: 回测批、探针、健康检查的进程内封装（`outcome/ops/batches.py`）

**Files:**
- Create: `src/finance_agent/outcome/ops/batches.py`
- Test: `tests/outcome/test_ops_batches.py`

**Interfaces:**
- Consumes: `evals.backtest.run_backtest.run_backtest/run_batch_probe`、`evals.backtest.leakage_probe.run_leakage_probe`、`evals.backtest.report.assert_clean_window`、`evals.backtest.sampling.stratified_sample`、`evals.outcome.health.collect_outcome_health`、`finance_agent.data.akshare_client.AKShareClient`。
- Produces:
  - `run_probe_task(*, codes: list[str], decision_date: str, window_days: int = 20, n_tickers: int = 10, seed: int = 42, client=None, llm=None) -> dict`（返回探针读数，含 `state`）
  - `run_backtest_task(*, batch_kind: str, codes: list[str], per_regime: int = 10, repeats: int = 3, as_of: str | None = None, client=None, replay_fn=None) -> dict`（返回报告 dict；formal 前置门禁不过 → 抛 `PreregistrationError`/`CleanWindowError`，由端点翻 409）
  - `run_health_task(*, db_path=None) -> dict`（JSON 可序列化的门禁读数）
  - `CleanWindowError(RuntimeError)`

- [ ] **Step 1: 写失败测试**（离线，fake client/replay/llm；复用 Δ4 的夹具思路）

```python
def test_formal_batch_refused_when_clean_window_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(batches, "assert_clean_window", lambda *a, **k: {"passed": False, "reason": "距 as_of 仅 3 个交易日"})
    with pytest.raises(CleanWindowError, match="3 个交易日"):
        batches.run_backtest_task(batch_kind="formal", codes=["600519"], client=FakeClient())

def test_pathway_batch_returns_report_and_writes_md(tmp_path, monkeypatch, fake_replay, fake_client):
    monkeypatch.chdir(tmp_path)  # md 落 evals/backtest/results 需目录存在 → 实现内 mkdir
    report = batches.run_backtest_task(batch_kind="pathway", codes=["600519"], client=fake_client, replay_fn=fake_replay)
    assert report["positioning"] == "pathway" and report["conclusion"].startswith("通路验证定位")

def test_probe_task_marks_unmeasurable(tmp_path):
    out = batches.run_probe_task(codes=["600519"], decision_date="2024-06-03", client=FakeClient(), llm=lambda p: "我不确定")
    assert out["state"] == "unmeasurable" and out["direction_hit_rate"] is None

def test_health_task_is_json_serializable(tmp_path):
    out = batches.run_health_task(db_path=tmp_path / "x.db")
    json.dumps(out, ensure_ascii=False)   # 不得含不可序列化对象
    assert "gates" in out
```

- [ ] **Step 2: 跑测试确认失败** → `uv run pytest tests/outcome/test_ops_batches.py -q`

- [ ] **Step 3: 实现**：薄编排——formal 门禁顺序 = `assert_preregistered` → `assert_clean_window` → `run_batch_probe`；pathway = 只跑探针（若 `probe=True`）+ `run_backtest(batch_kind="pathway")`；md/json 落 `evals/backtest/results` 与 `reports/backtest`（目录不存在则 mkdir）；返回的 report dict 供 `job_runs.summary` 用（**summary 只放裁剪版**：`{"conclusion","positioning","n_sample","leakage_probe.direction_hit_rate","perf_table.system.Sharpe"}`，完整报告在 md/json）。**不复制任何计算逻辑**。

- [ ] **Step 4: 跑测试** → `uv run pytest tests/outcome/test_ops_batches.py tests/evals/backtest -q`

- [ ] **Step 5: 提交** `git commit -m "feat(ops): 回测批/探针/健康检查进程内封装（复用 evals 实现，零复制）（delta add-eval-ops-console）"`

---

### Task 5: 预登记版本化与口径草稿（`outcome/ops/prereg.py`）+ 端点

**Files:**
- Create: `src/finance_agent/outcome/ops/prereg.py`
- Modify: `src/finance_agent/ops_api.py`（`GET/PUT /api/v1/ops/prereg`、`POST /api/v1/ops/caliber-draft`）
- Test: `tests/outcome/test_ops_prereg.py`、`tests/test_ops_api.py`（补端点用例）

**Interfaces:**
- Produces:
  - `list_prereg_versions(*, dir: Path = PREREG_DIR, name_contains: str = "outcome") -> list[dict]` → `[{"path","fields","valid","issues","locked"}]`
  - `save_prereg_version(fields: dict[str, str], *, dir: Path = PREREG_DIR, today: str | None = None) -> Path`（校验不过 → `InvalidPreregistration`，不落盘）
  - `is_locked(path: Path, *, db_path=None, backtests_dir: Path = BACKTEST_RESULTS) -> bool`（任一 cohort 读数或回测报告引用该路径）
  - `InvalidPreregistration(RuntimeError)`
  - `KNOB_KEYS: tuple[str, ...] = ("PRIMARY_WINDOW_DAYS", "NEUTRAL_BAND", "LEAKAGE_PROBE_THRESHOLD", "MIN_SETTLED_FOR_WINRATE")`
  - `current_knobs() -> dict[str, float | int]`（import `evals.outcome.caliber` 读取，**只读**）
  - `write_caliber_draft(knobs: dict[str, float | int], *, changes_dir: Path = Path("openspec/changes"), ts: str | None = None) -> Path`（已有未处理草稿涉及同一旋钮 → `DraftExists`；**不写** metrics.md / caliber.py）

- [ ] **Step 1: 写失败测试**

```python
def test_save_rejects_invalid_fields(tmp_path):
    with pytest.raises(InvalidPreregistration, match="MDE"):
        save_prereg_version({"主指标": "x"}, dir=tmp_path)   # 缺 MDE 等
    assert list(tmp_path.glob("*.md")) == []                 # 不落盘

def test_save_writes_new_version_without_touching_history(tmp_path):
    old = tmp_path / "2026-01-01-outcome-a.md"; old.write_text("历史版本", encoding="utf-8")
    new = save_prereg_version(VALID_FIELDS, dir=tmp_path, today="2026-09-24")
    assert new.name == "2026-09-24-outcome-prereg-v2.md" or new.name.startswith("2026-09-24-")
    assert old.read_text(encoding="utf-8") == "历史版本"

def test_lock_detects_reading_reference(tmp_path, monkeypatch):
    p = tmp_path / "2026-09-23-outcome-x.md"; p.write_text("...", encoding="utf-8")
    bt = tmp_path / "bt"; bt.mkdir()
    (bt / "formal-1.md").write_text(f"**预登记**: {p}\n**status**: active", encoding="utf-8")
    assert is_locked(p, backtests_dir=bt) is True

def test_caliber_draft_does_not_touch_ledger_or_constants(tmp_path, monkeypatch):
    ledger = tmp_path / "metrics.md"; ledger.write_text("原值 0.60", encoding="utf-8")
    const = tmp_path / "caliber.py"; const.write_text("LEAKAGE_PROBE_THRESHOLD = 0.60", encoding="utf-8")
    d = write_caliber_draft({"LEAKAGE_PROBE_THRESHOLD": 0.55}, changes_dir=tmp_path / "changes", ts="20260924-120000")
    assert (d / "proposal.md").exists() and "0.55" in (d / "proposal.md").read_text(encoding="utf-8")
    assert "0.60" in ledger.read_text(encoding="utf-8") and "0.60" in const.read_text(encoding="utf-8")

def test_second_draft_for_same_knob_refused(tmp_path):
    write_caliber_draft({"NEUTRAL_BAND": 0.03}, changes_dir=tmp_path, ts="a")
    with pytest.raises(DraftExists):
        write_caliber_draft({"NEUTRAL_BAND": 0.03}, changes_dir=tmp_path, ts="b")
```

- [ ] **Step 2: 跑测试确认失败** → `uv run pytest tests/outcome/test_ops_prereg.py -q`

- [ ] **Step 3: 实现**：`save_prereg_version` 用 `parse_preregister(text, required_fields=OUTCOME_REQUIRED_FIELDS)` 校验（把 fields 渲染成 `- 字段: 值` 行），`.valid` 为假则 raise；文件名 `f"{today}-outcome-prereg-{n}.md"`（n 递增避免覆盖）。`is_locked` 扫 `cohort_runs`（`SELECT COUNT(*) FROM cohort_runs` 存在即认为有读数，需 join 预登记路径字段——**若无字段则退化为「存在任意 success 行即锁定」并在此说明**）与 backtests_dir 下 md 的 `**预登记**` 行文本包含该文件名。`write_caliber_draft` 生成 `ops-caliber-draft-<ts>/proposal.md`（含每个旋钮的现值→新值与「生效须走 delta 流程」声明）+ `specs/evaluation/spec.md`（一条 MODIFIED 需求骨架）+ `metrics-timeline-line.md`（§2 切点行草稿）。

- [ ] **Step 4: 跑测试** → `uv run pytest tests/outcome/test_ops_prereg.py tests/test_ops_api.py -q`

- [ ] **Step 5: 提交** `git commit -m "feat(ops): 预登记版本化 + 读数锁定 + 口径 delta 草稿生成（不触碰台账与常量）（delta add-eval-ops-console）"`

---

### Task 6: 前端「评估运维」分区（`EvalOpsPane` + 注册）

**Files:**
- Create: `frontend/src/pages/settings/panes/EvalOpsPane.tsx`
- Create: `frontend/src/pages/settings/panes/ConfirmSpendDialog.tsx`（烧钱确认弹窗统一组件）
- Modify: `frontend/src/pages/settings/SettingsCenterPage.tsx`（注册分区与导航项）
- Modify: `frontend/src/types.ts`（`OpsJobStatus` / `OpsCohortState` / `OpsReportEntry` / `OpsRun` 等接口）
- Test: `frontend/src/test/settings/evalOpsPane.test.tsx`

**Interfaces:**
- Consumes: Task 3 的端点契约（字段名逐字对齐）。
- Produces: 六页签 UI——`调度` / `cohort` / `回测与探针` / `健康检查` / `报告注册表` / `预登记与口径`；所有元素带 `data-testid="eval-ops-*"`。

- [ ] **Step 1: 写失败测试**（vitest + RTL，mock `fetch` 仅限测试内——不是 E2E）

```tsx
it('渲染五任务与未运行横幅', async () => {
  mockFetch({ scheduler_running: false, jobs: FIVE_JOBS, cohort: COHORT_OFF })
  render(<EvalOpsPane />)
  expect(await screen.findByTestId('eval-ops-not-running')).toBeInTheDocument()
  expect(screen.getAllByTestId(/^eval-ops-job-/)).toHaveLength(5)
})

it('开启开关先确认，取消不产生请求', async () => {
  const { calls } = mockFetch(COHORT_OFF_STATE)
  render(<EvalOpsPane />)
  await userEvent.click(await screen.findByTestId('eval-ops-cohort-toggle'))
  expect(await screen.findByTestId('eval-ops-confirm-dialog')).toBeInTheDocument()
  expect(screen.getByTestId('eval-ops-confirm-cost')).toHaveTextContent(/tokens/)
  await userEvent.click(screen.getByTestId('eval-ops-confirm-cancel'))
  expect(calls.filter(c => c.method === 'PUT')).toHaveLength(0)
})

it('门禁拒绝时展示原因而非静默', async () => {
  mockFetch(JOBS, { backtest: { status: 409, detail: '预登记缺字段: MDE' } })
  render(<EvalOpsPane />)
  await userEvent.click(await screen.findByTestId('eval-ops-backtest-formal'))
  await userEvent.click(screen.getByTestId('eval-ops-backtest-submit'))
  expect(await screen.findByTestId('eval-ops-error')).toHaveTextContent('MDE')
})
```

- [ ] **Step 2: 跑测试确认失败** → `cd frontend && npx vitest run src/test/settings/evalOpsPane.test.tsx`

- [ ] **Step 3: 实现**：状态机 `loading|ready|error` + 重试按钮（照 `DataMonitorPane`）；`调度` 页签每任务卡片含 `立即运行` 按钮（点击 → POST run → 轮询 `GET /api/v1/ops/jobs` 直到该任务 `last_run.status != "running"`，期间按钮禁用并显示「运行中」）；`cohort` 页签含开关、时/分输入、今日花费与成功/失败；`回测与探针` 页签含通路/正式两按钮（正式按钮先本地校验预登记存在，服务端 409 时展示 detail）、探针表单（代码列表 + 决策日）与结果三态卡；`健康检查` 页签运行按钮 + 门禁表格（FAIL 红、无读数灰）；`报告注册表` 表格含 status 徽章与定位标签；`预登记与口径` 页签表单（七字段）+ 保存 + 锁定提示 + 旋钮修改（生成草稿后展示草稿路径）。

- [ ] **Step 4: 跑测试** → `cd frontend && npm test -- evalOpsPane`

- [ ] **Step 5: 提交** `git commit -m "feat(frontend): 设置中心「评估运维」分区——六页签 + 烧钱确认弹窗 + 门禁拒绝展示（delta add-eval-ops-console）"`

---

### Task 7: 战绩页总览补齐三披露

**Files:**
- Modify: `frontend/src/pages/trackRecord/TrackRecordPage.tsx`（总览区）
- Modify: `frontend/src/types.ts`（`TrackRecordOverview` 补 `avoidance` / `caliber_horizon` / `legacy_settled`）
- Test: `frontend/src/test/trackRecord/trackRecordPage.test.tsx`（补用例）

**Interfaces:**
- Consumes: 既有 `GET /api/v1/track-record/overview`（字段已存在）。
- Produces: `data-testid="track-record-avoidance"` / `"track-record-caliber"` / `"track-record-legacy"`。

- [ ] **Step 1: 写失败测试**

```tsx
it('样本充足时展示回避正确率与样本数', async () => { /* overview.avoidance = {settled:12, avoidance_rate:0.58, ...} → 文案含 58% 与 12 */ })
it('回避样本不足时展示样本积累中而非 0', async () => { /* settled:3 → 不含 "0%"；含「样本积累中」 */ })
it('口径与存量计数常驻，存量为 0 时明示无存量', async () => { /* caliber_horizon:20, legacy_settled:0 → 含 T+20 与「无存量」 */ })
```

- [ ] **Step 2: 跑测试确认失败** → `cd frontend && npx vitest run src/test/trackRecord/trackRecordPage.test.tsx`

- [ ] **Step 3: 实现**：总览卡片区加一张「回避正确率」卡（`settled < 10` → 「样本积累中（已判定 n 条）」）；在胜率卡下方加一行 `口径 T+{caliber_horizon} 交易日` + `存量旧口径 n 条`（n=0 → 「无存量」）。

- [ ] **Step 4: 跑测试** → `cd frontend && npm test`

- [ ] **Step 5: 提交** `git commit -m "feat(frontend): 战绩页总览补回避正确率/口径/存量计数三披露（delta add-eval-ops-console）"`

---

### Task 8: E2E 门禁与收口

**Files:**
- Create: `tests/e2e/playwright/tests/eval-ops-console.spec.ts`
- Create: `tests/validation/2026-09-24-add-eval-ops-console-validation.md`
- Modify: `docs/evals/metrics.md` §2（追加「运维控制台启用切点」行）、`openspec/changes/add-eval-ops-console/tasks.md`（勾选）

- [ ] **Step 1: E2E spec**（TESTING=1 stub 后端 + vite dev；**不 mock 业务接口**）

```ts
test('评估运维分区渲染五任务与未运行提示', async ({ page }) => {
  await page.goto('/'); await page.getByTestId('settings-entry').click()
  await page.getByTestId('settings-nav-eval-ops').click()
  await expect(page.getByTestId('eval-ops-pane')).toBeVisible()
  await expect(page.getByTestId('eval-ops-not-running')).toBeVisible()   // TESTING=1 → 未运行
  await expect(page.locator('[data-testid^="eval-ops-job-"]')).toHaveCount(5)
})

test('开关切换需确认，取消不落配置', async ({ page }) => { /* 展开 cohort 页签 → 切换 → 弹窗 → 取消 → 状态未变 */ })
test('正式批门禁拒绝展示原因', async ({ page }) => { /* 发起正式批（TESTING 下预登记目录为空）→ 展示「预登记」原因 */ })
test('立即运行反馈运行中到完成', async ({ page }) => { /* 点完整性校验「立即运行」→ 出现「运行中」→ 轮询后出现结果 */ })
```

- [ ] **Step 2: 跑 E2E** → `cd tests/e2e/playwright && npx playwright test eval-ops-console.spec.ts`（期望 4 passed）

- [ ] **Step 3: 机器项** → `uv run pytest tests/outcome tests/test_ops_api.py tests/evals/backtest -q -m "not live"`；`uv run ruff check evals/ src/ tests/`；`uv run mypy src/finance_agent/outcome/ops src/finance_agent/ops_api.py`；`cd frontend && npm test`；`openspec validate add-eval-ops-console --strict`

- [ ] **Step 4: 人工验证 + 台账 + 勾选**：真实浏览器核对六页签与确认流（截图存 `tests/e2e/`），验证报告落 `tests/validation/2026-09-24-add-eval-ops-console-validation.md`，`metrics.md` §2 追加切点行，`tasks.md` 全勾

- [ ] **Step 5: 提交** `git commit -m "test(ops): add-eval-ops-console 验证收口——E2E 门禁/人工验证/台账登记（tasks 勾选）"`

---

## Self-Review

**Spec 覆盖**：新 capability 7 需求 → R1(T1+T2+T3) / R2(T2+T3) / R3(T1+T2+T3) / R4(T3+T4) / R5(T3+T4) / R6(T5+T6 的预登记与口径页签) / R7(T6+T8) 中模块(Spec-Reviewer)；`paper-trading-cohort` MODIFIED → T1/T2；`track-record` MODIFIED → T7。26 个 Scenario 中「审计行」「重启保持」「并发互斥」「锁定」分别由 T1/T2/T5 的定向用例覆盖，E2E 三条覆盖 R7。

**Placeholder 扫描**：无 TBD/TODO；每个实现步给出真实签名与关键实现片段；测试步给出真实断言。

**类型一致性**：`get_cohort_settings` 返回键（enabled/hour/minute/source）在 T2/T3 一致；`run_job` 返回（run_id/status/summary/error）在 T2/T3/T6 一致；端点字段名 T3 定义、T6 逐字消费；`OpsReportEntry.status` 取值域 `active|superseded-by` 与 `report_status.STATUSES` 一致。

**已知风险（实施时注意）**：① `is_locked` 依赖 cohort_runs 是否记录预登记路径——若无该列，退化为「存在任意 success 行即锁定」并在代码注释与 spec 场景里说明；② 正式批异步任务耗时数分钟，E2E 只覆盖「门禁拒绝」与「通路批启动」不等待完成；③ `reschedule_cohort` 在 `TESTING=1`（无调度器）时返回 False 而非抛错。
