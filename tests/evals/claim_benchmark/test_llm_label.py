"""标注流程测试：LLM 初标字段追加、人工合并 κ 定稿、空 label 拒绝。"""

import json
from argparse import Namespace
from pathlib import Path

from evals.claim_benchmark import llm_label


def _entry(eid: str, stated=10.0, gt=10.0, delta=0.0) -> dict:
    return {
        "entry_id": eid,
        "claim": {
            "claim_type": "numerical",
            "source_type": "data",
            "field_ref": "x",
            "stated_value": stated,
            "interpretation": "",
        },
        "ground_truth": gt,
        "delta": delta,
        "subsets": ["clean"],
    }


def _write(path: Path, entries: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


class FakeArgs(Namespace):
    """Namespace 子类：cmd_* 的 argparse.Namespace 形参可直接接收 kwargs 构造。"""


class TestLabel:
    def test_appends_llm_label_and_reason(self, tmp_path: Path, monkeypatch):
        inp = tmp_path / "in.jsonl"
        out = tmp_path / "out.jsonl"
        _write(inp, [_entry("e1")])
        monkeypatch.setattr(
            llm_label, "_call_llm", lambda prompt: '{"label": "PASS", "reason": "容差内"}'
        )
        rc = llm_label.cmd_label(FakeArgs(input=str(inp), out=str(out)))
        assert rc == 0
        rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
        assert rows[0]["llm_label"] == "PASS"
        assert rows[0]["llm_reason"] == "容差内"

    def test_parse_failure_falls_back_unverifiable(self, tmp_path: Path, monkeypatch):
        inp = tmp_path / "in.jsonl"
        out = tmp_path / "out.jsonl"
        _write(inp, [_entry("e1")])
        monkeypatch.setattr(llm_label, "_call_llm", lambda prompt: "not json")
        llm_label.cmd_label(FakeArgs(input=str(inp), out=str(out)))
        rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
        assert rows[0]["llm_label"] == "UNVERIFIABLE"


class TestFinalize:
    def test_kappa_high_llm_final(self, tmp_path: Path, monkeypatch):
        """人工抽检一致（κ=1）→ LLM 标签定稿。"""
        inp = tmp_path / "in.jsonl"
        out = tmp_path / "out.jsonl"
        entries = [_entry("e1"), _entry("e2")]
        entries[0]["llm_label"] = "PASS"
        entries[1]["llm_label"] = "FAIL"
        _write(inp, entries)
        human = tmp_path / "h.csv"
        human.write_text("entry_id,human_label\ne1,PASS\ne2,FAIL\n", encoding="utf-8")
        llm_label.cmd_finalize(FakeArgs(input=str(inp), human=str(human), out=str(out)))
        rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
        assert [r["label"] for r in rows] == ["PASS", "FAIL"]

    def test_kappa_low_human_overrides_disagreement(self, tmp_path: Path, monkeypatch):
        """κ<0.8 时分歧以人工为准。"""
        inp = tmp_path / "in.jsonl"
        out = tmp_path / "out.jsonl"
        entries = [_entry("e1"), _entry("e2")]
        entries[0]["llm_label"] = "PASS"
        entries[1]["llm_label"] = "FAIL"
        _write(inp, entries)
        human = tmp_path / "h.csv"
        human.write_text("entry_id,human_label\ne1,FAIL\ne2,FAIL\n", encoding="utf-8")
        llm_label.cmd_finalize(FakeArgs(input=str(inp), human=str(human), out=str(out)))
        rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
        assert rows[0]["label"] == "FAIL"  # 分歧覆盖
        assert rows[1]["label"] == "FAIL"

    def test_no_empty_label_allowed(self, tmp_path: Path):
        inp = tmp_path / "in.jsonl"
        out = tmp_path / "out.jsonl"
        _write(inp, [_entry("e1")])
        human = tmp_path / "h.csv"
        human.write_text("entry_id,human_label\n", encoding="utf-8")
        try:
            llm_label.cmd_finalize(FakeArgs(input=str(inp), human=str(human), out=str(out)))
        except SystemExit as e:
            assert "label 为空" in str(e)
        else:  # pragma: no cover
            raise AssertionError("空 label 必须拒绝")
