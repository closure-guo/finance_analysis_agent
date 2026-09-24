"""Task 3(delta add-eval-ops-console):``/api/v1/ops`` 端点族。

覆盖面:
1. 五任务状态与运行历史——含定时重试「每次尝试各一行」时的 ``last_run`` 取最新行、
   进程重启遗留悬挂 ``running`` 行的清扫、cohort 行与 ``cohort`` 块时刻一致;
2. 手动补跑——202 + run_id;未知任务 404;锁占用/开关关闭 409;**任务失败非 2xx**
   （失败不伪装成 202 成功,原因随响应与运行历史双通道可见）;
3. cohort 开关与时刻——PUT 持久化 + 即时重排 + config-change 审计行（旧值→新值）
   + 越界 422;
4. 异步长任务（回测/探针/健康检查）——立即 202 返回 run_id,结果经
   ``GET /runs/{run_id}`` 读取（裁剪 summary:完整报告在 md/json）;同类并发 409;
5. 报告注册表——只读 status 头 + 定位标签 + 探针方向命中率;
6. 事件循环不被阻塞（状态接口与长任务派发均不得阻塞 asyncio 循环）+ 启动引导。

全部用例零网络零 LLM:batch 层任务函数经 ``ops_api._resolve_batch_func`` 注入假实现
（Task 4 落地的真实实现由 ``tests/outcome/test_ops_batches.py`` 的接线用例兜住）;
调度器句柄逐用例复位——不依赖其它测试模块（如 test_track_record_metrics 的
``TestSchedulerJobs``）可能泄漏的 Mock 句柄。
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from finance_agent import ops_api
from finance_agent.api import app
from finance_agent.outcome.cohort.model import init_cohort_runs, insert_cohort_run
from finance_agent.outcome.ops.jobs import (
    JOB_FUNCS,
    JOB_IDS,
    SCHEDULES,
    CohortDisabled,
    JobAlreadyRunning,
)
from finance_agent.outcome.ops.model import (
    COHORT_HOUR_KEY,
    COHORT_MINUTE_KEY,
    finish_job_run,
    get_config,
    insert_job_run,
    last_job_run,
    list_job_runs,
    set_config,
)

BASE = "/api/v1/ops"

# 有效 outcome 预登记正文（七个门禁字段齐备 + 决策阈值带换算依据）
_PREREG_BODY = "\n".join(
    [
        "- 主指标: 逐决策 T+20 相对沪深300 超额收益均值与胜率",
        "- MDE: n=30 → 5.1pp（换算依据见 §4）",
        "- 决策阈值: 均值超额 95% CI 下限 > 0；依据：标的簇 bootstrap CI",
        "- 样本量依据: forward ≥10 / ≥30 / ≥100（MDE 反算）",
        "- 停止规则: 健康检查不过作废；探针 >0.60 降级",
        "- 成本分型: forward 每标的 1 次 deep；回测 回放 ×3 + 探针",
        "- 泄漏控制: 干净窗口 + 探针披露（阈值 0.60）",
    ]
)


# ── 夹具 ──


@pytest.fixture(autouse=True)
def _clean_scheduler_handle():
    """逐用例复位 scheduler 句柄(防其它测试模块的 Mock 泄漏影响「是否运行」判定)。"""
    import finance_agent.outcome.scheduler as scheduler_mod

    old = scheduler_mod._scheduler
    scheduler_mod._scheduler = None
    try:
        yield
    finally:
        scheduler_mod._scheduler = old


@pytest.fixture(autouse=True)
def _restore_cohort_schedule_snapshot():
    """SCHEDULES 是调度器启动期刷新的模块级快照,用例改过后复原(测试隔离)。"""
    spec = dict(SCHEDULES["cohort_batch"])
    try:
        yield
    finally:
        SCHEDULES["cohort_batch"].update(spec)


@pytest.fixture(autouse=True)
def _testing_env(monkeypatch):
    """TESTING=1(调度器不启动)+ cohort 开关回到「未配置」(默认关)。"""
    monkeypatch.setenv("TESTING", "1")
    for name in ("COHORT_ENABLED", "COHORT_HOUR", "COHORT_MINUTE"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def patch_batch_funcs(monkeypatch):
    """按名注入 batch 层假实现;端点解析到未注入的名字 → AssertionError(强断言无外溢调用)。"""

    def _install(mapping: dict):
        def _resolve(name: str):
            assert name in mapping, f"端点解析了未注入的 batch 函数: {name}"
            return mapping[name]

        monkeypatch.setattr(ops_api, "_resolve_batch_func", _resolve)

    return _install


@pytest.fixture
def prereg_dir(tmp_path) -> Path:
    """有效预登记目录(真实过 assert_preregistered 门禁)。"""
    directory = tmp_path / "preregister"
    directory.mkdir()
    (directory / "2026-01-01-outcome-prereg.md").write_text(_PREREG_BODY, encoding="utf-8")
    return directory


def _db() -> Path:
    return Path(os.environ["SESSIONS_DB_PATH"])


def _seed_run(
    job_id: str,
    *,
    kind: str = "manual",
    status: str = "ok",
    summary: dict | None = None,
    error: str | None = None,
    source: str | None = None,
) -> int:
    """落一条终态运行历史(真实走 insert + finish 两段)。"""
    run_id = insert_job_run(
        job_id,
        kind,
        "running",
        source=source or ("manual" if kind == "manual" else "scheduled"),
        db_path=_db(),
    )
    finish_job_run(run_id, status=status, summary=summary, error=error, db_path=_db())
    return run_id


def _job(body: dict, job_id: str) -> dict:
    return next(j for j in body["jobs"] if j["job_id"] == job_id)


def _wait_run(client: TestClient, run_id: int, timeout: float = 5.0) -> dict:
    """轮询 GET /runs/{id} 直到离开 running(异步任务完成)。"""
    deadline = time.time() + timeout
    body: dict = {}
    while time.time() < deadline:
        resp = client.get(f"{BASE}/runs/{run_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        if body["status"] != "running":
            return body
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} 超时未完成: {body}")


class _FakeTask:
    """可调用假任务:记录入参,返回固定结果或抛异常。"""

    def __init__(self, result: dict | None = None, exc: BaseException | None = None) -> None:
        self.result = result or {}
        self.exc = exc
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        return self.result


# ── 1. 状态与运行历史 ──


class TestJobsEndpoint:
    def test_reports_not_running_under_testing(self, client):
        body = client.get(f"{BASE}/jobs").json()
        assert body["scheduler_running"] is False
        assert [j["job_id"] for j in body["jobs"]] == list(JOB_IDS)
        assert all(j["next_fire_time"] is None for j in body["jobs"])
        assert all(j["label"] for j in body["jobs"])
        for job in body["jobs"]:
            assert set(job["schedule"]) == {"day_of_week", "hour", "minute", "timezone"}
            assert job["last_run"] is None and job["history"] == []

    def test_last_run_and_history_shape(self, client):
        run_id = _seed_run("integrity_check", summary={"issues": 0})
        job = _job(client.get(f"{BASE}/jobs").json(), "integrity_check")
        assert job["last_run"]["run_id"] == run_id
        assert job["last_run"]["status"] == "ok"
        assert job["last_run"]["summary"] == {"issues": 0}
        assert job["last_run"]["finished_at"] is not None
        assert [h["run_id"] for h in job["history"]] == [run_id]

    def test_last_run_takes_newest_of_retry_attempts(self, client):
        """定时失败每次尝试各留一行(3 行)——last_run 取最新行,history 保留全部。"""
        ids = [
            _seed_run(
                "decision_settle_daily", kind="scheduled", status="failed", error=f"attempt {i}"
            )
            for i in range(3)
        ]
        # 最终行标注重试次数(scheduler._mark_retries 语义)
        finish_job_run(
            ids[-1], status="failed", summary={"attempts": 3, "retries": 2}, db_path=_db()
        )
        job = _job(client.get(f"{BASE}/jobs").json(), "decision_settle_daily")
        assert job["last_run"]["run_id"] == ids[-1]
        assert job["last_run"]["summary"] == {"attempts": 3, "retries": 2}
        assert [h["run_id"] for h in job["history"]] == list(reversed(ids))
        assert all(h["status"] == "failed" for h in job["history"])

    def test_history_is_bounded_and_newest_first(self, client):
        ids = [
            _seed_run("metrics_snapshot", summary={"i": i})
            for i in range(ops_api.HISTORY_LIMIT + 3)
        ]
        job = _job(client.get(f"{BASE}/jobs").json(), "metrics_snapshot")
        assert [h["run_id"] for h in job["history"]] == list(
            reversed(ids[-ops_api.HISTORY_LIMIT :])
        )

    def test_stale_running_swept_on_read(self, client, monkeypatch):
        """进程重启遗留的 running 行:读到状态时收尾为 failed(stale_process_restart)。"""
        stale = insert_job_run("daily_marking", "scheduled", "running", source="scheduled")
        # 模拟「本进程启动晚于该行」——只有更早启动的进程遗留行才会满足
        monkeypatch.setattr(
            ops_api, "_PROCESS_STARTED_AT", (datetime.now() + timedelta(minutes=5)).isoformat()
        )
        job = _job(client.get(f"{BASE}/jobs").json(), "daily_marking")
        assert job["last_run"]["run_id"] == stale
        assert job["last_run"]["status"] == "failed"
        assert job["last_run"]["finished_at"] is not None
        assert "stale_process_restart" in (job["last_run"]["error"] or "")
        assert job["last_run"]["summary"]["reason"] == "stale_process_restart"

    def test_live_running_row_not_swept(self, client):
        """本进程正在跑的行不得被清扫(否则并发轮询会把补跑误标为失败)。"""
        live = insert_job_run("daily_marking", "manual", "running", source="manual")
        job = _job(client.get(f"{BASE}/jobs").json(), "daily_marking")
        assert job["last_run"]["run_id"] == live
        assert job["last_run"]["status"] == "running"

    def test_cohort_job_row_agrees_with_cohort_block(self, client):
        """cohort 行不得渲染调度器启动期的陈旧快照,须与 cohort 块同源(不可能互相矛盾)。"""
        SCHEDULES["cohort_batch"].update({"hour": 7, "minute": 5})  # 陈旧快照
        set_config(COHORT_HOUR_KEY, "19", _db())
        set_config(COHORT_MINUTE_KEY, "30", _db())
        body = client.get(f"{BASE}/jobs").json()
        job = _job(body, "cohort_batch")
        assert (job["schedule"]["hour"], job["schedule"]["minute"]) == (19, 30)
        assert (job["schedule"]["hour"], job["schedule"]["minute"]) == (
            body["cohort"]["hour"],
            body["cohort"]["minute"],
        )
        # 结算链四任务时刻不受影响
        assert _job(body, "decision_settle_daily")["schedule"]["hour"] == 16

    def test_cohort_block_fields(self, client):
        body = client.get(f"{BASE}/jobs").json()
        assert set(body["cohort"]) == {
            "enabled",
            "hour",
            "minute",
            "budget_tokens",
            "today_spend",
            "today_success",
            "today_failure",
        }
        assert body["cohort"]["enabled"] is False
        assert body["cohort"]["hour"] == 18 and body["cohort"]["minute"] == 0
        assert body["cohort"]["budget_tokens"] > 0

    def test_cohort_block_counts_today_spend(self, client):
        init_cohort_runs(_db())
        day = datetime.now().strftime("%Y-%m-%d")
        for ticker, status, tokens in (
            ("600519", "success", 1200),
            ("000858", "failure", None),
            ("300308", "skipped", None),
            ("600000", "success", 300),
        ):
            insert_cohort_run(
                {
                    "universe_version": "v1",
                    "ticker": ticker,
                    "trade_date": day,
                    "status": status,
                    "tokens_total": tokens,
                    "trigger_time": datetime.now().isoformat(),
                },
                _db(),
            )
        # 昨日行不计入今日花费
        insert_cohort_run(
            {
                "universe_version": "v1",
                "ticker": "002412",
                "trade_date": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
                "status": "success",
                "tokens_total": 9999,
                "trigger_time": datetime.now().isoformat(),
            },
            _db(),
        )
        block = client.get(f"{BASE}/cohort").json()
        assert block["today_spend"] == 1500
        assert block["today_success"] == 2 and block["today_failure"] == 1


# ── 2. 手动补跑 ──


class TestManualRun:
    def test_ok_returns_202_and_lands_history(self, client, monkeypatch):
        monkeypatch.setitem(JOB_FUNCS, "integrity_check", lambda: {"issues": 0})
        resp = client.post(f"{BASE}/jobs/integrity_check/run")
        assert resp.status_code == 202
        run_id = resp.json()["run_id"]
        assert isinstance(run_id, int)
        job = _job(client.get(f"{BASE}/jobs").json(), "integrity_check")
        assert job["last_run"]["run_id"] == run_id
        assert job["last_run"]["status"] == "ok"
        assert job["last_run"]["summary"] == {"issues": 0}
        assert job["last_run"]["kind"] == "manual"
        assert job["last_run"]["source"] == "manual"
        # run 详情可读(单条运行接口)
        detail = client.get(f"{BASE}/runs/{run_id}").json()
        assert detail["run_id"] == run_id and detail["summary"] == {"issues": 0}

    def test_failed_run_is_non_2xx_with_reason(self, client, monkeypatch):
        """任务失败返回 dict(status=failed)不抛——端点必须翻成非 2xx,不得伪装成功。"""

        def boom():
            raise RuntimeError("db locked")

        monkeypatch.setitem(JOB_FUNCS, "daily_marking", boom)
        resp = client.post(f"{BASE}/jobs/daily_marking/run")
        assert resp.status_code == 500
        assert "db locked" in resp.json()["detail"]
        job = _job(client.get(f"{BASE}/jobs").json(), "daily_marking")
        assert job["last_run"]["status"] == "failed"
        assert "db locked" in job["last_run"]["error"]

    def test_already_running_409(self, client, monkeypatch):
        def busy(job_id, **_kwargs):
            raise JobAlreadyRunning(f"{job_id} 已在运行")

        monkeypatch.setattr(ops_api, "run_job", busy)
        resp = client.post(f"{BASE}/jobs/integrity_check/run")
        assert resp.status_code == 409
        assert resp.json()["detail"] == "already_running"

    def test_cohort_disabled_409_and_zero_llm(self, client):
        """开关关:手动跑批拒绝(零 LLM 调用),历史留 skipped-disabled 行。"""
        resp = client.post(f"{BASE}/jobs/cohort_batch/run")
        assert resp.status_code == 409
        assert resp.json()["detail"] == "cohort_disabled"
        row = last_job_run("cohort_batch", _db())
        assert row["status"] == "skipped-disabled"

    def test_unknown_job_404(self, client):
        assert client.post(f"{BASE}/jobs/nope/run").status_code == 404

    def test_unknown_run_404(self, client):
        assert client.get(f"{BASE}/runs/999999").status_code == 404


# ── 3. cohort 开关与时刻 ──


class TestCohortControl:
    def test_put_persists_reschedules_and_audits(self, client, monkeypatch):
        calls: list[tuple[int, int]] = []
        monkeypatch.setattr(ops_api, "reschedule_cohort", lambda h, m: calls.append((h, m)) or True)
        resp = client.put(f"{BASE}/cohort", json={"enabled": True, "hour": 19, "minute": 30})
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True and resp.json()["rescheduled"] is True
        assert calls == [(19, 30)]
        # 持久化(重启保持语义:表值是运行期唯一真源)
        assert get_config(COHORT_HOUR_KEY, _db()) == "19"
        assert get_config(COHORT_MINUTE_KEY, _db()) == "30"
        assert client.get(f"{BASE}/cohort").json()["minute"] == 30
        # 审计行:旧值→新值
        audits = [
            r for r in list_job_runs("cohort_batch", db_path=_db()) if r["kind"] == "config-change"
        ]
        assert len(audits) == 1
        assert audits[0]["status"] == "ok" and audits[0]["finished_at"] is not None
        assert audits[0]["summary"]["from"] == {"enabled": False, "hour": 18, "minute": 0}
        assert audits[0]["summary"]["to"] == {"enabled": True, "hour": 19, "minute": 30}
        assert resp.json()["audit_run_id"] == audits[0]["run_id"]

    def test_put_partial_update_keeps_other_keys(self, client, monkeypatch):
        monkeypatch.setattr(ops_api, "reschedule_cohort", lambda h, m: True)
        client.put(f"{BASE}/cohort", json={"hour": 20})
        body = client.get(f"{BASE}/cohort").json()
        assert (body["hour"], body["minute"], body["enabled"]) == (20, 0, False)

    def test_put_rejects_out_of_range(self, client):
        assert client.put(f"{BASE}/cohort", json={"hour": 24}).status_code == 422
        assert client.put(f"{BASE}/cohort", json={"minute": 60}).status_code == 422
        assert client.put(f"{BASE}/cohort", json={"enabled": "maybe"}).status_code == 422
        assert get_config(COHORT_HOUR_KEY, _db()) is None

    def test_put_records_audit_even_without_scheduler(self, client):
        """TESTING(无调度器)下配置仍须落库 + 留审计,rescheduled=False 如实返回。"""
        resp = client.put(f"{BASE}/cohort", json={"hour": 9, "minute": 5})
        assert resp.status_code == 200
        assert resp.json()["rescheduled"] is False
        assert resp.json()["hour"] == 9


# ── 4. 异步长任务(回测/探针/健康检查) ──


class TestAsyncTasks:
    def test_backtest_pathway_returns_202_and_trimmed_summary(self, client, patch_batch_funcs):
        fat = {
            "conclusion": "通路验证定位（batch_kind=pathway）：本批不产出 skill / 赚钱能力结论句",
            "positioning": "pathway",
            "batch_kind": "pathway",
            "n_sample": 3,
            "n_consistent": 2,
            "clean_window": None,
            "leakage_probe": {
                "state": "measurable",
                "direction_hit_rate": 0.3,
                "unknown_ratio": 0.1,
                "downgraded": False,
                "threshold": 0.6,
                "probe_n": 10,
                "details": [{"huge": "x" * 50}],
            },
            "perf_table": {
                "system": {"CR": 0.1, "ARR": 0.2, "Sharpe": 1.5, "MDD": 0.2},
                "buy_hold": {"Sharpe": 0.7},
            },
            "consistency": {"per_symbol": [{"code": "600519"}]},
            "methodology": {"entry": "..."},
            "report_paths": {
                "md": "evals/backtest/results/pathway-1.md",
                "json": "reports/backtest/x.json",
            },
        }
        fake = _FakeTask(result=fat)
        patch_batch_funcs({"run_backtest_task": fake})

        resp = client.post(
            f"{BASE}/backtest",
            json={"batch_kind": "pathway", "codes": ["600519"], "per_regime": 1},
        )
        assert resp.status_code == 202
        run = _wait_run(client, resp.json()["run_id"])
        assert run["job_id"] == "backtest" and run["status"] == "ok"
        summary = run["summary"]
        # 裁剪版字段路径齐备
        assert summary["conclusion"] == fat["conclusion"]
        assert summary["positioning"] == "pathway"
        assert summary["n_sample"] == 3 and summary["n_consistent"] == 2
        assert summary["leakage_probe"]["direction_hit_rate"] == 0.3
        assert summary["perf_table"]["system"]["Sharpe"] == 1.5
        assert summary["report_paths"]["md"].endswith(".md")
        # 体积大的明细不进 summary(完整报告在 md/json)
        assert "details" not in summary["leakage_probe"]
        assert "consistency" not in summary
        assert "buy_hold" not in summary["perf_table"]
        assert len(json.dumps(summary, ensure_ascii=False)) < 2000
        # 端点把请求透传给任务
        assert fake.calls[0]["batch_kind"] == "pathway"
        assert fake.calls[0]["codes"] == ["600519"]
        assert fake.calls[0]["per_regime"] == 1

    def test_backtest_formal_refused_without_preregistration(self, client, monkeypatch, tmp_path):
        """空预登记目录:同步门禁拒绝(409 + 原因),不解析/派发任何 batch 函数。"""
        monkeypatch.setattr(ops_api, "PREREGISTER_DIR", tmp_path / "preregister")
        resolved: list[str] = []

        def _resolve(name: str):
            resolved.append(name)
            return _FakeTask(result={"conclusion": "不应跑到这里"})

        monkeypatch.setattr(ops_api, "_resolve_batch_func", _resolve)
        resp = client.post(f"{BASE}/backtest", json={"batch_kind": "formal", "codes": ["600519"]})
        assert resp.status_code == 409
        assert "预登记" in resp.json()["detail"]
        assert resolved == []
        assert list_job_runs("backtest", db_path=_db()) == []

    def test_backtest_formal_clean_window_refusal_409(
        self, client, monkeypatch, prereg_dir, patch_batch_funcs
    ):
        """预登记有效但干净窗口拒绝 → 409 + 原因(而非 202 后静默失败),且不派发任务。"""

        class _CleanWindowRefusalError(RuntimeError):
            pass

        def _preflight(**_kwargs):
            raise _CleanWindowRefusalError("决策日 2024-06-03 距 as_of 仅 3 个交易日")

        monkeypatch.setattr(ops_api, "PREREGISTER_DIR", prereg_dir)
        patch_batch_funcs({"prepare_backtest": _preflight})
        monkeypatch.setattr(
            ops_api,
            "_is_clean_window_refusal",
            lambda exc: isinstance(exc, _CleanWindowRefusalError),
        )
        resp = client.post(
            f"{BASE}/backtest", json={"batch_kind": "formal", "codes": ["600519"], "per_regime": 1}
        )
        assert resp.status_code == 409
        assert "3 个交易日" in resp.json()["detail"]
        # 门禁未通过:不派发任务(无运行历史行、无回放)
        assert list_job_runs("backtest", db_path=_db()) == []

    def test_backtest_formal_dispatches_with_prepared_gate_result(
        self, client, monkeypatch, prereg_dir, patch_batch_funcs
    ):
        """门禁通过:prepare_backtest 的结果随任务透传(不重复取数/不重复判定)。"""
        prepared = {"sample": [{"code": "600519", "regime": "bull", "decision_date": "x"}]}
        prepare = _FakeTask(result=prepared)
        task = _FakeTask(result={"conclusion": "上界证据", "positioning": "skill"})
        monkeypatch.setattr(ops_api, "PREREGISTER_DIR", prereg_dir)
        patch_batch_funcs({"prepare_backtest": prepare, "run_backtest_task": task})
        resp = client.post(
            f"{BASE}/backtest", json={"batch_kind": "formal", "codes": ["600519"], "per_regime": 1}
        )
        assert resp.status_code == 202
        assert _wait_run(client, resp.json()["run_id"])["status"] == "ok"
        assert prepare.calls[0]["batch_kind"] == "formal"
        assert task.calls[0]["prepared"] is prepared

    def test_backtest_task_failure_recorded_not_202_success(self, client, patch_batch_funcs):
        """异步任务内部失败:运行记录如实 failed(端点已 202,失败经 /runs/{id} 可见)。"""
        patch_batch_funcs({"run_backtest_task": _FakeTask(exc=RuntimeError("采样失败"))})
        resp = client.post(f"{BASE}/backtest", json={"batch_kind": "pathway", "codes": ["600519"]})
        assert resp.status_code == 202
        run = _wait_run(client, resp.json()["run_id"])
        assert run["status"] == "failed"
        assert "采样失败" in run["error"]

    def test_probe_returns_readings_without_details(self, client, patch_batch_funcs):
        reading = {
            "state": "unmeasurable",
            "probe_n": 3,
            "questions_per_ticker": 3,
            "direction_hit_rate": None,
            "magnitude_hit_rate": None,
            "event_hit_rate": None,
            "unknown_ratio": 1.0,
            "threshold": 0.6,
            "downgraded": False,
            "probe_window": ["2024-06-03"],
            "per_window": [{"probe_window": ["2024-06-03"], "state": "unmeasurable"}],
            "details": [{"ticker": "600519", "prompt": "x" * 5000}],
        }
        fake = _FakeTask(result=reading)
        patch_batch_funcs({"run_probe_task": fake})
        resp = client.post(
            f"{BASE}/probe", json={"codes": ["600519"], "decision_date": "2024-06-03"}
        )
        assert resp.status_code == 202
        run = _wait_run(client, resp.json()["run_id"])
        assert run["status"] == "ok" and run["job_id"] == "probe"
        summary = run["summary"]
        # 不可测态如实为 null(不折算 0),逐窗口明细保留,逐题 details 不进 summary
        assert summary["state"] == "unmeasurable"
        assert summary["direction_hit_rate"] is None
        assert summary["unknown_ratio"] == 1.0
        assert summary["per_window"]
        assert "details" not in summary
        assert fake.calls[0]["decision_date"] == "2024-06-03"

    def test_probe_requires_codes_and_decision_date(self, client):
        assert (
            client.post(
                f"{BASE}/probe", json={"codes": [], "decision_date": "2024-06-03"}
            ).status_code
            == 422
        )
        assert client.post(f"{BASE}/probe", json={"codes": ["600519"]}).status_code == 422
        assert (
            client.post(
                f"{BASE}/probe",
                json={"codes": ["600519"], "decision_date": "2024-06-03", "window_days": 0},
            ).status_code
            == 422
        )

    def test_health_dispatch_passes_gates_summary(self, client, patch_batch_funcs):
        """健康检查结果(门禁读数)原样入 summary:缺失读数如实为 None,不冒充 0/100%。"""
        reading = {
            "db": "x.db",
            "available": True,
            "passed": False,
            "gates": [
                {
                    "id": "settlement_success",
                    "label": "结算成功率",
                    "value": None,
                    "threshold": ">= 0.9",
                    "passed": False,
                    "reason": "无已结算样本（无读数）",
                },
                {
                    "id": "integrity",
                    "label": "快照完整性",
                    "value": 0,
                    "threshold": "== 0",
                    "passed": True,
                    "reason": "无不一致",
                },
            ],
        }
        patch_batch_funcs({"run_health_task": _FakeTask(result=reading)})
        resp = client.post(f"{BASE}/health")
        assert resp.status_code == 202
        run = _wait_run(client, resp.json()["run_id"])
        assert run["status"] == "ok" and run["job_id"] == "health"
        assert run["summary"] == reading
        settlement = next(g for g in run["summary"]["gates"] if g["id"] == "settlement_success")
        assert settlement["value"] is None and settlement["passed"] is False

    def test_same_kind_concurrent_refused(self, client, monkeypatch):
        gate = threading.Event()

        def slow(**_kwargs):
            gate.wait(3)
            return {"state": "measurable", "direction_hit_rate": 0.5}

        monkeypatch.setattr(ops_api, "_resolve_batch_func", lambda _name: slow)
        first = client.post(
            f"{BASE}/probe", json={"codes": ["600519"], "decision_date": "2024-06-03"}
        )
        assert first.status_code == 202
        try:
            second = client.post(
                f"{BASE}/probe", json={"codes": ["600519"], "decision_date": "2024-06-03"}
            )
            assert second.status_code == 409
            assert second.json()["detail"] == "already_running"
        finally:
            gate.set()
        assert _wait_run(client, first.json()["run_id"])["status"] == "ok"
        # 锁释放后同类任务可再次派发
        third = client.post(
            f"{BASE}/probe", json={"codes": ["600519"], "decision_date": "2024-06-03"}
        )
        assert third.status_code == 202
        _wait_run(client, third.json()["run_id"])


# ── 5. 报告注册表 ──


class TestReportsRegistry:
    def test_registry_reads_status_header(self, client):
        body = client.get(f"{BASE}/reports").json()
        assert isinstance(body, list) and body
        assert any(item["name"].startswith("pilot-2023-shock") for item in body)
        assert all(item["status"] in ("active", "superseded-by") for item in body)
        pilot = next(i for i in body if i["name"].startswith("pilot-2023-shock"))
        assert set(pilot) == {
            "name",
            "path",
            "status",
            "target",
            "positioning",
            "probe_direction_hit_rate",
        }
        assert pilot["positioning"] == "pathway"  # 正文标注「通路验证」
        assert pilot["path"].endswith("evals/backtest/results/pilot-2023-shock.md")

    def test_registry_reads_positioning_and_probe_rate(self, client, monkeypatch, tmp_path):
        results = tmp_path / "results"
        results.mkdir()
        (results / "formal-1.md").write_text(
            "\n".join(
                [
                    "# 回测报告：formal-1",
                    "**status**: superseded-by: pathway-2.md",
                    "**批次类型**: formal",
                    "- 方向命中率 direction_hit_rate：12.5%（阈值 threshold：60%）",
                    "泄漏污染下的上界证据（真实 skill ≤ 读数）：无显著差异",
                ]
            ),
            encoding="utf-8",
        )
        (results / "pathway-2.md").write_text(
            "\n".join(
                [
                    "# 回测报告：pathway-2",
                    "**status**: active",
                    "**批次类型**: pathway",
                    "- 方向命中率 direction_hit_rate：80%（阈值 threshold：60%）",
                    "通路验证定位（batch_kind=pathway）：本批不产出 skill 结论句",
                ]
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(ops_api, "BACKTEST_RESULTS_DIR", results)
        body = client.get(f"{BASE}/reports").json()
        by_name = {i["name"]: i for i in body}
        assert by_name["formal-1"]["status"] == "superseded-by"
        assert by_name["formal-1"]["target"] == "pathway-2.md"
        assert by_name["formal-1"]["positioning"] == "upper_bound"
        assert by_name["formal-1"]["probe_direction_hit_rate"] == 0.125
        assert by_name["pathway-2"]["positioning"] == "pathway"
        assert by_name["pathway-2"]["probe_direction_hit_rate"] == 0.8

    def test_registry_missing_dir_is_empty_not_error(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(ops_api, "BACKTEST_RESULTS_DIR", tmp_path / "nope")
        assert client.get(f"{BASE}/reports").json() == []

    def test_registry_flags_defective_report_loudly(self, client, monkeypatch, tmp_path):
        """superseded-by 缺目标是有缺陷的报告,不得静默跳过(整表显式报错)。"""
        results = tmp_path / "results"
        results.mkdir()
        (results / "broken.md").write_text(
            "# 回测报告：broken\n**status**: superseded-by\n", encoding="utf-8"
        )
        monkeypatch.setattr(ops_api, "BACKTEST_RESULTS_DIR", results)
        resp = client.get(f"{BASE}/reports")
        assert resp.status_code == 500
        assert "报告注册表" in resp.json()["detail"]


# ── 6. 事件循环不被阻塞 + 启动引导 ──


class TestEventLoopAndLifespan:
    async def test_status_endpoint_does_not_block_event_loop(self, monkeypatch):
        def slow_payload():
            time.sleep(0.5)
            return {"scheduler_running": False, "jobs": [], "cohort": {}}

        monkeypatch.setattr(ops_api, "_jobs_payload", slow_payload)
        wakeups = 0

        async def ticker():
            nonlocal wakeups
            while True:
                await asyncio.sleep(0.05)
                wakeups += 1

        task = asyncio.create_task(ticker())
        body = await ops_api.get_jobs()
        await asyncio.sleep(0.1)
        task.cancel()
        assert wakeups >= 5, f"事件循环被阻塞(唤醒 {wakeups} 次)"
        assert body["jobs"] == []

    async def test_long_task_dispatch_returns_without_blocking(self, monkeypatch):
        def slow_task(**_kwargs):
            time.sleep(0.5)
            return {"conclusion": "ok", "positioning": "pathway"}

        monkeypatch.setattr(ops_api, "_resolve_batch_func", lambda _name: slow_task)
        wakeups = 0

        async def ticker():
            nonlocal wakeups
            while True:
                await asyncio.sleep(0.05)
                wakeups += 1

        task = asyncio.create_task(ticker())
        started = time.time()
        body = await ops_api.trigger_backtest(
            ops_api.BacktestRequest(batch_kind="pathway", codes=["600519"])
        )
        elapsed = time.time() - started
        assert body["run_id"]
        assert elapsed < 0.3, f"派发阻塞了 {elapsed:.2f}s"
        # 长任务仍在后台线程运行(0.5s)期间,事件循环必须照常唤醒
        await asyncio.sleep(0.4)
        task.cancel()
        assert wakeups >= 4, f"事件循环被阻塞(唤醒 {wakeups} 次)"

    def test_lifespan_bootstraps_cohort_config_from_env(self, monkeypatch):
        """启动引导:env 只在表内缺失时落表(重启保持),端点随即读到。"""
        monkeypatch.setenv("TESTING", "1")  # 防真调度器被拉起
        monkeypatch.setenv("COHORT_ENABLED", "1")
        monkeypatch.setenv("COHORT_HOUR", "20")
        monkeypatch.delenv("COHORT_MINUTE", raising=False)
        with TestClient(app) as c:
            body = c.get(f"{BASE}/cohort").json()
        assert body["enabled"] is True and body["hour"] == 20 and body["minute"] == 0
        # 已有表值不被引导覆盖
        set_config(COHORT_MINUTE_KEY, "45", _db())
        with TestClient(app) as c:
            assert c.get(f"{BASE}/cohort").json()["minute"] == 45


def test_job_already_running_and_cohort_disabled_are_runtime_errors():
    """端点映射依赖的异常类型(回归护栏)。"""
    assert issubclass(JobAlreadyRunning, RuntimeError)
    assert issubclass(CohortDisabled, RuntimeError)
