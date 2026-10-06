"""add-prediction-pool-integrity Task 6:/api/v1/track-record/significance 只读端点。"""

from fastapi.testclient import TestClient

from finance_agent.api import app
from finance_agent.outcome.track_record.model import (
    init_track_record_tables,
    insert_prediction,
    update_prediction_status,
)

BASE = {
    "source_type": "live",
    "symbol": "600519.SH",
    "symbol_name": "贵州茅台",
    "direction": "long",
    "entry_price": 100.0,
    "horizon_days": 20,
    "confidence": 0.8,
    "rationale_snapshot": {"action": "buy"},
    "created_at": "2026-11-01T10:00:00",
}


def _use_db(monkeypatch, tmp_path):
    """DB 隔离:tmp 库 + patch _default_db_path(与 tests/test_api_track_record.py 同模式)。"""
    db = tmp_path / "sig.db"
    init_track_record_tables(db)
    monkeypatch.setattr("finance_agent.outcome.track_record.model._default_db_path", lambda: db)
    return db


def _insert(db, **overrides):
    rec = dict(BASE)
    rec.update(overrides)
    return insert_prediction(rec, db_path=db)


def _settle(db, pid, status, month, **extra):
    """按月落判定(resolved_at 控制结算月,monthly_ic 按其[:7]聚合)。"""
    update_prediction_status(
        pid, {"status": status, "resolved_at": f"{month}-15T10:00:00", **extra}, db_path=db
    )


def test_significance_empty_db_insufficient_state(monkeypatch, tmp_path):
    """空库:序列为空、icir 为 null、monte_carlo available=false 带原因。

    契约(§1.9-v2「结论必附分位」):响应形态上不存在孤立的点估计或分位字段——
    端点永不单独返回点估计。
    """
    _use_db(monkeypatch, tmp_path)
    resp = TestClient(app).get("/api/v1/track-record/significance")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ic_series"] == [] and body["avoidance_series"] == []
    assert body["icir"] is None
    mc = body["monte_carlo"]
    assert mc["available"] is False and mc["reason"]
    assert "excess_point_estimate" not in body
    assert not ({"excess_point_estimate", "quantile", "p_value"} & set(mc))


def test_significance_duplicate_rows_never_enter_ic_series(monkeypatch, tmp_path):
    """duplicate_of_day 行(即便带 resolved_at)不进 ic_series——日主口径。"""
    db = _use_db(monkeypatch, tmp_path)
    _settle(db, _insert(db, symbol="a.SH"), "resolved_win", "2026-11")
    _settle(db, _insert(db, symbol="b.SH"), "resolved_loss", "2026-11")
    dup = _insert(db, symbol="dup.SH")
    update_prediction_status(
        dup,
        {
            "status": "duplicate_of_day",
            "resolution_rule": "duplicate_of_day",
            "resolved_at": "2026-11-15T10:00:00",
        },
        db_path=db,
    )
    body = TestClient(app).get("/api/v1/track-record/significance").json()
    assert len(body["ic_series"]) == 1
    assert body["ic_series"][0]["sample"] == 2  # duplicate 行不计入分子分母


def test_significance_monthly_series_and_insufficient_marking(monkeypatch, tmp_path):
    """月度聚合:10 判定(7win)期 ic=0.7 样本足;6 判定期 insufficient 标注;期数不足 icir=null。"""
    db = _use_db(monkeypatch, tmp_path)
    for i in range(10):
        _settle(
            db,
            _insert(db, symbol=f"n{i}.SH"),
            "resolved_win" if i < 7 else "resolved_loss",
            "2026-11",
        )
    for i in range(6):
        _settle(
            db,
            _insert(db, symbol=f"m{i}.SH"),
            "resolved_win" if i < 4 else "resolved_loss",
            "2026-12",
        )
    body = TestClient(app).get("/api/v1/track-record/significance").json()
    series = body["ic_series"]
    assert [s["month"] for s in series] == ["2026-11", "2026-12"]
    assert series[0]["sample"] == 10
    assert series[0]["ic"] == 0.7
    assert series[0]["insufficient"] is False
    assert series[1]["sample"] == 6
    assert series[1]["insufficient"] is True  # 单期样本 <10 标注,不进 ICIR
    assert body["icir"] is None  # 有效期数 < 6 → SHALL NOT 展示


def test_significance_avoidance_separate_column_not_in_direction_ic(monkeypatch, tmp_path):
    """neutral 回避行单独成列(avoidance_series),SHALL NOT 混入方向 ic_series。"""
    db = _use_db(monkeypatch, tmp_path)
    for i in range(3):
        pid = _insert(db, symbol=f"aw{i}.SH", direction="neutral")
        update_prediction_status(
            pid,
            {
                "status": "avoidance",
                "avoidance_status": "avoidance_win",
                "resolved_at": "2026-11-15T10:00:00",
            },
            db_path=db,
        )
    _settle(db, _insert(db, symbol="l.SH"), "resolved_win", "2026-11")
    body = TestClient(app).get("/api/v1/track-record/significance").json()
    assert len(body["ic_series"]) == 1 and body["ic_series"][0]["sample"] == 1
    assert len(body["avoidance_series"]) == 1
    assert body["avoidance_series"][0]["sample"] == 3
    assert body["avoidance_series"][0]["wins"] == 3


def test_significance_beyond_100_rows_oldest_month_not_truncated(monkeypatch, tmp_path):
    """回归(P1):已判定行 >100 时最老月份不得被 list_predictions 旧钳制静默丢弃。

    生产库 predictions 已 127 行,首批结算报告恰是受害时点。旧钳制
    min(limit,100) 下端点只取到最新 100 行 → 2026-07 整月(最老 10 行)消失;
    放宽上限后最老月份须完整进入 ic_series。
    """
    db = _use_db(monkeypatch, tmp_path)
    for i in range(10):  # 最老月 2026-07,created_at 全库最早
        pid = _insert(db, symbol=f"old{i}.SH", created_at=f"2026-07-{i + 1:02d}T10:00:00")
        _settle(db, pid, "resolved_win" if i < 7 else "resolved_loss", "2026-07")
    for i in range(100):  # 次月 100 行,created_at 均晚于 2026-07 组
        pid = _insert(
            db, symbol=f"new{i}.SH", created_at=f"2026-08-01T{i // 60:02d}:{i % 60:02d}:00"
        )
        _settle(db, pid, "resolved_win" if i % 2 else "resolved_loss", "2026-08")
    body = TestClient(app).get("/api/v1/track-record/significance").json()
    months = [s["month"] for s in body["ic_series"]]
    assert months == ["2026-07", "2026-08"]  # 最老月份不得被截断
    assert body["ic_series"][0]["sample"] == 10
    assert body["ic_series"][0]["ic"] == 0.7
    assert body["ic_series"][1]["sample"] == 100
