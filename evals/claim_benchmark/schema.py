"""断言级校验基准集 schema（spec evaluation「断言级校验基准集」）。

数据文件：seed.jsonl（每行一条 BenchmarkEntry）+ meta.json（版本/规模/κ）。
种子集为合成确定性数据（annotator=synthetic-seed），标注语义待人工双人标注
替换/扩充（meta.notes 说明）；滚动补库 = 追加行 + version 递增。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from evals.stats import cohen_kappa

_DIR = Path(__file__).resolve().parent


class BenchmarkEntry(BaseModel):
    entry_id: str
    state_key: str  # fixtures.build_state 的 key
    claim: dict  # Claim.model_dump()
    label_final: Literal["PASS", "FAIL", "UNVERIFIABLE"]
    label_a: str | None = None
    label_b: str | None = None
    annotator_a: str = "synthetic-seed"
    annotator_b: str = "synthetic-seed"
    subsets: list[str] = Field(default_factory=list)  # borderline / hedged


class BenchmarkMeta(BaseModel):
    version: str
    n_reports: int
    n_claims: int
    kappa: float | None = None
    notes: str = ""


def load_entries() -> list[BenchmarkEntry]:
    lines = (_DIR / "seed.jsonl").read_text(encoding="utf-8").splitlines()
    return [BenchmarkEntry.model_validate(json.loads(line)) for line in lines if line.strip()]


def load_meta() -> BenchmarkMeta:
    return BenchmarkMeta.model_validate(
        json.loads((_DIR / "meta.json").read_text(encoding="utf-8"))
    )


def compute_kappa(entries: list[BenchmarkEntry]) -> float | None:
    """存在真实双人标注（双方 annotator 非 synthetic）时计算 κ；否则 None。"""
    dual = [
        e
        for e in entries
        if e.label_a
        and e.label_b
        and "synthetic" not in e.annotator_a
        and "synthetic" not in e.annotator_b
    ]
    if not dual:
        return None
    return cohen_kappa([e.label_a or "" for e in dual], [e.label_b or "" for e in dual])
