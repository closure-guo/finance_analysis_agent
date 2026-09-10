"""断言级金标准集 schema（spec assertion-golden-set）。

硬约束：as_of_date / origin 缺失拒绝入库；annotator=rule_derived 仅允许 pilot 层
（真实准度只由人工标注样本声明，构造标签只能当回归探针）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

_DEFAULT_PATH = Path(__file__).parent / "data" / "assertion-golden-v1.jsonl"

TIERS = ("smoke", "core", "adversarial", "pilot")
TYPES = (
    "fact_extraction",
    "numeric_reasoning",
    "table_text_grounding",
    "trajectory",
    "point_in_time",
    "refusal_boundary",
    "multi_turn",
    "adversarial",
    "settlement_rule",
)
ANNOTATORS = ("double_human", "single_human", "rule_derived")
JUDGE_TYPES = ("rule", "trajectory", "llm_judge")


class GoldenEntry(BaseModel):
    """单条金标准样本。判定优先 deterministic(rule/trajectory)，禁 rule_derived 做准度证据。"""

    id: str
    type: str
    tier: Literal["smoke", "core", "adversarial", "pilot"]
    input: str
    dialog_history: list[dict] = Field(default_factory=list)
    context: dict  # as_of_date / market / entities
    expected: dict
    judge_type: Literal["rule", "trajectory", "llm_judge"]
    tags: list[str] = Field(default_factory=list)
    origin: str
    added_in: str = "v1.0"
    annotator: Literal["double_human", "single_human", "rule_derived"]
    pit_checked: bool = False

    @model_validator(mode="after")
    def _require_meta(self) -> GoldenEntry:
        if not (self.context or {}).get("as_of_date"):
            raise ValueError(f"{self.id}: as_of_date 缺失，不得入库（金融数据有时效）")
        if not self.origin.strip():
            raise ValueError(f"{self.id}: origin 缺失，不得入库（出处可追溯）")
        if self.annotator == "rule_derived" and self.tier != "pilot":
            raise ValueError(f"{self.id}: rule_derived 标签仅允许 pilot 层，不得作生产准度证据")
        if self.judge_type == "llm_judge":
            cal = self.expected.get("judge_calibration") or {}
            if not cal.get("rubric_version") or not cal.get("human_agreement"):
                raise ValueError(
                    f"{self.id}: llm_judge 样本必须带 judge_calibration(rubric_version/human_agreement)"
                )
        return self


def load_entries(path: Path | None = None, tier: str | None = None) -> list[GoldenEntry]:
    """读取金标准集（一行一条）；tier 给定则过滤。校验失败即抛错（拒绝坏样本入库）。"""
    p = path or _DEFAULT_PATH
    entries: list[GoldenEntry] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = GoldenEntry.model_validate(json.loads(line))
        if tier is None or entry.tier == tier:
            entries.append(entry)
    return entries
