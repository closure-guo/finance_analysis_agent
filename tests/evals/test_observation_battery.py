"""常规观测电池（delta add-causal-observation-battery）。

固定 P1 快照 × 当前生产栈 → grounding / B1 / B2 三读数；观测不裁决（无层间结论句）；
快照 digest 不一致显式失败；rubric 未过校准门 → provisional。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from evals.causal_ablation import observation as ob
from evals.causal_ablation import pilot_runner as pr


def _fake_product(dir_: Path, ticker: str, digest: str) -> None:
    pr.save_product(
        pr.product_path(dir_, ticker), {"snapshot": {"k": ticker}, "snapshot_digest": digest}
    )


def _fake_graph_runner(*, variant: str, snapshot: dict, query: str) -> dict:  # noqa: ARG001
    return {"query": query, "report": "r"}


def _judge_yes(prompt: str) -> str:  # noqa: ARG001
    return json.dumps({"supported": True, "absorbed": True, "corrected": True, "reason": "ok"})


class TestSnapshotDigest:
    def test_mismatch_fails_explicitly_without_running(self, tmp_path, monkeypatch):
        snap = tmp_path / "snap"
        snap.mkdir()
        for t, d in [("600519", "digest-a"), ("000001", "digest-b")]:
            _fake_product(snap, t, d)
        runner = MagicMock()
        monkeypatch.setattr(
            ob,
            "run_materials",
            runner,  # 任何材料腿入口都不应被触达
        )
        with pytest.raises(ob.SnapshotDriftError) as exc:
            ob.run_battery(
                ["600519", "000001"],
                snapshot_dir=snap,
                out_dir=tmp_path / "out",
                expected_digests={"600519": "digest-a", "000001": "digest-X"},
                graph_runner=runner,
                judge_fn=_judge_yes,
            )
        msg = str(exc.value)
        assert "000001" in msg and "digest-b" in msg and "digest-X" in msg
        runner.assert_not_called()

    def test_match_proceeds(self, tmp_path):
        snap = tmp_path / "snap"
        snap.mkdir()
        for t in ("600519", "000001"):
            _fake_product(snap, t, "d1")
        result = ob.run_battery(
            ["600519", "000001"],
            snapshot_dir=snap,
            out_dir=tmp_path / "out",
            expected_digests={"600519": "d1", "000001": "d1"},
            graph_runner=_fake_graph_runner,
            judge_fn=_judge_yes,
        )
        assert result["snapshot_digests"] == {"600519": "d1", "000001": "d1"}
        assert set(result["readings"]) == {"grounding", "b1_absorption", "b2_correction"}


class TestReadings:
    def test_rate_from_labels(self):
        rows = [
            {"judge_label": True},
            {"judge_label": False},
            {"judge_label": True},
            {"judge_label": None},  # 解析失败不入分母
        ]
        assert ob._rate_from_labels(rows) == pytest.approx(2 / 3, abs=1e-3)
        assert ob._rate_from_labels([]) is None

    def test_reading_shape_carries_denominators(self):
        """读数含分母行数与解析失败数（spec「一键跑观测电池」）。"""
        rows = [{"judge_label": True, "rubric": "b1-v1"}, {"judge_label": False, "rubric": "b1-v1"}]
        reading = ob._reading("b1_absorption", rows, registry={"b1-v1": {}})
        assert reading["rows"] == 2
        assert reading["positive"] == 1
        assert reading["parse_failed"] == 0
        assert reading["rate"] == 0.5
        assert reading["provisional"] is False

    def test_no_layer_increment_fields_in_result(self, tmp_path):
        """观测不裁决：产物不含层增量/裁决字段（spec「观测轮不作层增量」）。"""
        snap = tmp_path / "snap"
        snap.mkdir()
        _fake_product(snap, "600519", "d1")
        result = ob.run_battery(
            ["600519"],
            snapshot_dir=snap,
            out_dir=tmp_path / "out",
            graph_runner=_fake_graph_runner,
            judge_fn=_judge_yes,
        )
        result.pop("out_dir", None)  # 路径可能撞禁词，只扫读数与结构字段
        flat = json.dumps(result, ensure_ascii=False)
        for banned in ("increment", "diff_mean", "verdict", "层增量"):
            assert banned not in flat
        assert set(result) >= {"tickers", "snapshot_digests", "readings", "llm_calls"}

    def test_provisional_when_rubric_not_in_registry(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ob, "CALIBRATION_REGISTRY", {})  # 无任何校准记录
        snap = tmp_path / "snap"
        snap.mkdir()
        _fake_product(snap, "600519", "d1")
        result = ob.run_battery(
            ["600519"],
            snapshot_dir=snap,
            out_dir=tmp_path / "out",
            graph_runner=_fake_graph_runner,
            judge_fn=_judge_yes,
        )
        for name in ("grounding", "b1_absorption", "b2_correction"):
            assert result["readings"][name]["provisional"] is True, name
        assert result["readings"]["b1_absorption"]["rubric"] == "b1-v1"


class TestRunsJsonlLine:
    def test_line_parses_with_required_fields(self, tmp_path):
        snap = tmp_path / "snap"
        snap.mkdir()
        _fake_product(snap, "600519", "d1")
        result = ob.run_battery(
            ["600519"],
            snapshot_dir=snap,
            out_dir=tmp_path / "out",
            graph_runner=_fake_graph_runner,
            judge_fn=_judge_yes,
        )
        line = ob.runs_jsonl_line(result, started_at="2026-09-22T00:00:00Z", git_head="abc1234")
        row = json.loads(line)
        assert row["run"].startswith("causal-observation-")
        assert row["git_head"] == "abc1234"
        assert row["means"]["llm_calls"]["materials"] in (0, None)  # 无 meter 时如实记 None
        assert "llm_calls" in row["means"]
        assert "report" in row
        assert "\n" not in line


class TestCli:
    def test_defaults(self):
        args = ob.parse_args([])
        assert args.snapshot_dir == Path("reports/ablation/p1/materials")
        assert len(args.tickers) == 20
        assert "600519" in args.tickers

    def test_ticker_subset(self):
        args = ob.parse_args(["--tickers", "600519", "000001"])
        assert args.tickers == ["600519", "000001"]
