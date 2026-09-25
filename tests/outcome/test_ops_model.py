"""Task 1(delta add-eval-ops-console):ops_config / job_runs 两表 + cohort 配置解析器。

表值优先 → env 引导 → 内置默认;越界/非数值回退 + WARN(_env_int 同款语义)。
运行历史 append + 终态更新;prune 每 job 保留最新 N 行。
"""

from __future__ import annotations

import logging
import sqlite3

import pytest

from finance_agent.outcome.ops.model import (
    COHORT_ENABLED_KEY,
    COHORT_HOUR_KEY,
    COHORT_MINUTE_KEY,
    bootstrap_cohort_from_env,
    finish_job_run,
    get_cohort_settings,
    get_config,
    init_ops,
    insert_job_run,
    last_job_run,
    list_job_runs,
    prune_job_runs,
    set_config,
)


def _tables(db) -> set[str]:
    conn = sqlite3.connect(db)
    try:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def test_init_ops_is_idempotent(tmp_path):
    db = tmp_path / "ops.db"
    init_ops(db)
    init_ops(db)  # 第二次不得抛
    assert set(_tables(db)) >= {"ops_config", "job_runs"}


def test_config_roundtrip_and_missing_key(tmp_path):
    db = tmp_path / "ops.db"
    init_ops(db)
    assert get_config("cohort_hour", db) is None
    set_config("cohort_hour", "19", db)
    assert get_config("cohort_hour", db) == "19"


def test_config_set_overwrites_same_key(tmp_path):
    db = tmp_path / "ops.db"
    init_ops(db)
    set_config("cohort_hour", "19", db)
    set_config("cohort_hour", "20", db)  # 同键覆盖,不产生第二行
    assert get_config("cohort_hour", db) == "20"
    conn = sqlite3.connect(db)
    try:
        n = conn.execute("SELECT COUNT(*) FROM ops_config").fetchone()[0]
    finally:
        conn.close()
    assert n == 1


def test_cohort_settings_table_wins_over_env(tmp_path, monkeypatch):
    db = tmp_path / "ops.db"
    init_ops(db)
    monkeypatch.setenv("COHORT_ENABLED", "0")
    set_config(COHORT_ENABLED_KEY, "1", db)
    s = get_cohort_settings(db)
    assert (s["enabled"], s["source"]) == (True, "ops_config")


def test_cohort_settings_falls_back_to_env_then_default(tmp_path, monkeypatch):
    db = tmp_path / "ops.db"
    init_ops(db)
    monkeypatch.setenv("COHORT_ENABLED", "1")
    monkeypatch.setenv("COHORT_HOUR", "20")
    monkeypatch.delenv("COHORT_MINUTE", raising=False)
    s = get_cohort_settings(db)
    assert (s["enabled"], s["hour"], s["minute"], s["source"]) == (True, 20, 0, "env")


def test_cohort_settings_all_default_when_table_and_env_empty(tmp_path, monkeypatch):
    db = tmp_path / "ops.db"
    init_ops(db)
    monkeypatch.delenv("COHORT_ENABLED", raising=False)
    monkeypatch.delenv("COHORT_HOUR", raising=False)
    monkeypatch.delenv("COHORT_MINUTE", raising=False)
    s = get_cohort_settings(db)
    assert (s["enabled"], s["hour"], s["minute"], s["source"]) == (False, 18, 0, "default")


def test_cohort_settings_bad_env_value_falls_back_with_warn(tmp_path, monkeypatch, caplog):
    db = tmp_path / "ops.db"
    init_ops(db)
    monkeypatch.delenv("COHORT_ENABLED", raising=False)
    monkeypatch.delenv("COHORT_MINUTE", raising=False)
    monkeypatch.setenv("COHORT_HOUR", "abc")
    with caplog.at_level(logging.WARNING, logger="finance_agent.outcome.ops.model"):
        s = get_cohort_settings(db)
    assert s["hour"] == 18  # 默认
    assert any("COHORT_HOUR" in r.getMessage() for r in caplog.records)  # WARN 落日志


def test_cohort_settings_bad_table_value_falls_back_to_env(tmp_path, monkeypatch):
    db = tmp_path / "ops.db"
    init_ops(db)
    set_config(COHORT_HOUR_KEY, "99", db)  # 越界表值不得生效
    monkeypatch.setenv("COHORT_HOUR", "21")
    s = get_cohort_settings(db)
    assert (s["hour"], s["source"]) == (21, "env")


def test_bootstrap_writes_env_values_only_when_absent(tmp_path, monkeypatch):
    db = tmp_path / "ops.db"
    init_ops(db)
    monkeypatch.setenv("COHORT_ENABLED", "1")
    bootstrap_cohort_from_env(db)
    assert get_config(COHORT_ENABLED_KEY, db) == "1"
    set_config(COHORT_ENABLED_KEY, "0", db)
    bootstrap_cohort_from_env(db)  # 已有值不得覆盖(重启保持语义)
    assert get_config(COHORT_ENABLED_KEY, db) == "0"


def test_bootstrap_writes_hour_and_minute_and_skips_bad_env(tmp_path, monkeypatch):
    db = tmp_path / "ops.db"
    init_ops(db)
    monkeypatch.setenv("COHORT_HOUR", "20")
    monkeypatch.setenv("COHORT_MINUTE", "abc")  # 非法值不落表(留给解析器回退默认)
    bootstrap_cohort_from_env(db)
    assert get_config(COHORT_HOUR_KEY, db) == "20"
    assert get_config(COHORT_MINUTE_KEY, db) is None


def test_bootstrap_keeps_existing_table_value_over_env(tmp_path, monkeypatch):
    db = tmp_path / "ops.db"
    init_ops(db)
    set_config(COHORT_HOUR_KEY, "19", db)
    monkeypatch.setenv("COHORT_HOUR", "20")
    bootstrap_cohort_from_env(db)
    assert get_config(COHORT_HOUR_KEY, db) == "19"


def test_job_run_lifecycle_and_last_run(tmp_path):
    db = tmp_path / "ops.db"
    init_ops(db)
    rid = insert_job_run("cohort_batch", "scheduled", "running", db_path=db)
    finish_job_run(rid, status="ok", summary={"success": 10}, db_path=db)
    row = last_job_run("cohort_batch", db)
    assert row["status"] == "ok" and row["summary"]["success"] == 10
    assert row["finished_at"] is not None


def test_job_run_insert_defaults_and_missing_last_run(tmp_path):
    db = tmp_path / "ops.db"
    init_ops(db)
    rid = insert_job_run("daily_marking", "manual", "running", db_path=db)
    row = last_job_run("daily_marking", db)
    assert row["run_id"] == rid
    assert row["source"] == "scheduled"  # 缺省 source
    assert row["summary"] is None and row["error"] is None
    assert row["finished_at"] is None
    assert last_job_run("nope", db) is None


def test_finish_job_run_records_error_and_keeps_summary_when_omitted(tmp_path):
    db = tmp_path / "ops.db"
    init_ops(db)
    rid = insert_job_run("metrics_snapshot", "scheduled", "running", summary={"a": 1}, db_path=db)
    finish_job_run(rid, status="failed", error="RuntimeError: boom", db_path=db)
    row = last_job_run("metrics_snapshot", db)
    assert row["status"] == "failed" and row["error"] == "RuntimeError: boom"
    assert row["summary"] == {"a": 1}  # 未传 summary 不得清空


def test_list_job_runs_filters_and_orders_newest_first(tmp_path):
    db = tmp_path / "ops.db"
    init_ops(db)
    first = insert_job_run("integrity_check", "scheduled", "ok", db_path=db)
    second = insert_job_run("integrity_check", "manual", "running", db_path=db)
    insert_job_run("cohort_batch", "scheduled", "ok", db_path=db)
    rows = list_job_runs("integrity_check", limit=10, db_path=db)
    assert [r["run_id"] for r in rows] == [second, first]
    assert len(list_job_runs(db_path=db)) == 3


def test_job_run_summary_truncated_but_still_json(tmp_path):
    db = tmp_path / "ops.db"
    init_ops(db)
    rid = insert_job_run(
        "cohort_batch", "manual", "running", summary={"blob": "x" * 20000}, db_path=db
    )
    finish_job_run(rid, status="ok", db_path=db)
    conn = sqlite3.connect(db)
    try:
        raw = conn.execute("SELECT summary FROM job_runs WHERE run_id=?", (rid,)).fetchone()[0]
    finally:
        conn.close()
    assert len(raw) <= 8192
    # 超大 summary 退化为显式裁剪标记,读取侧仍是合法 JSON dict
    row = last_job_run("cohort_batch", db)
    assert row["summary"]["truncated"] is True


def test_job_run_summary_serializes_non_json_values(tmp_path):
    db = tmp_path / "ops.db"
    init_ops(db)
    rid = insert_job_run(
        "cohort_batch", "scheduled", "running", summary={"path": tmp_path}, db_path=db
    )
    finish_job_run(rid, status="ok", db_path=db)
    assert isinstance(last_job_run("cohort_batch", db)["summary"]["path"], str)


def test_prune_keeps_newest_per_job(tmp_path):
    db = tmp_path / "ops.db"
    init_ops(db)
    for _ in range(10):
        r = insert_job_run("integrity_check", "scheduled", "running", db_path=db)
        finish_job_run(r, status="ok", db_path=db)
    assert prune_job_runs(keep_per_job=3, db_path=db) == 7
    assert len(list_job_runs("integrity_check", limit=99, db_path=db)) == 3


def test_prune_is_per_job(tmp_path):
    db = tmp_path / "ops.db"
    init_ops(db)
    for _ in range(4):
        insert_job_run("integrity_check", "scheduled", "ok", db_path=db)
    for _ in range(2):
        insert_job_run("cohort_batch", "scheduled", "ok", db_path=db)
    assert prune_job_runs(keep_per_job=3, db_path=db) == 1  # 只裁 integrity_check 的第 4 行
    assert len(list_job_runs("integrity_check", limit=99, db_path=db)) == 3
    assert len(list_job_runs("cohort_batch", limit=99, db_path=db)) == 2


def test_prune_noop_when_under_keep(tmp_path):
    db = tmp_path / "ops.db"
    init_ops(db)
    insert_job_run("integrity_check", "scheduled", "ok", db_path=db)
    assert prune_job_runs(keep_per_job=500, db_path=db) == 0


def test_functions_self_init_without_explicit_init_ops(tmp_path, monkeypatch):
    """下游(Task 2/3)未显式 init_ops 时不得 no such table。"""
    db = tmp_path / "fresh.db"
    monkeypatch.delenv("COHORT_HOUR", raising=False)
    assert get_cohort_settings(db)["hour"] == 18
    rid = insert_job_run("integrity_check", "manual", "running", db_path=db)
    finish_job_run(rid, status="ok", db_path=db)
    assert last_job_run("integrity_check", db)["status"] == "ok"


@pytest.mark.parametrize("bad_key", ["cohort_hour", "cohort_minute"])
def test_bad_table_int_value_is_ignored(tmp_path, bad_key, monkeypatch):
    db = tmp_path / "ops.db"
    init_ops(db)
    monkeypatch.delenv("COHORT_HOUR", raising=False)
    monkeypatch.delenv("COHORT_MINUTE", raising=False)
    set_config(bad_key, "not-a-number", db)
    s = get_cohort_settings(db)
    assert s["hour"] == 18 and s["minute"] == 0
