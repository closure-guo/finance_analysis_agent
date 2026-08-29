"""确定性生成 seed.jsonl（不调 LLM；真值由 citation 契约从 fixture 重算得出）。

覆盖：numerical PASS/FAIL（含 borderline/hedged 对抗条目）、computational 7 根键
PASS/FAIL/borderline/hedged、llm_inference UNVERIFIABLE、未注册根键 UNVERIFIABLE。
comparative/event 类型暂未生成，待生产基准集滚动补库时补齐。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from evals.claim_benchmark.fixtures import build_state
from evals.claim_benchmark.schema import BenchmarkEntry
from finance_agent.citation import _COMPUTATIONAL_RECALC

_DIR = Path(__file__).resolve().parent

Label = Literal["PASS", "FAIL", "UNVERIFIABLE"]


def _claims_for_root(state: dict, root: str) -> list[tuple[dict, Label, list[str]]]:
    """返回 (claim, label, subsets) 列表：PASS 一条 + 对抗 FAIL 一条（含 borderline/hedged 变体）。"""
    truth = _COMPUTATIONAL_RECALC[root](state)
    out: list[tuple[dict, Label, list[str]]] = []
    leaf = _first_leaf(truth)
    if leaf is None:
        return out
    path, gt = leaf
    ref = ".".join([root, *path])
    out.append(
        (
            {
                "claim_type": "computational",
                "source_type": "data",
                "field_ref": ref,
                "stated_value": round(gt, 6),
                "interpretation": "",
            },
            "PASS",
            [],
        )
    )
    out.append(
        (
            {
                "claim_type": "computational",
                "source_type": "data",
                "field_ref": ref,
                "stated_value": round(gt * 1.5, 6),
                "interpretation": "",
            },
            "FAIL",
            [],
        )
    )
    # borderline：真值 +2%（容差 0.5% 之外、±5% 之内）→ 应判 FAIL 的对抗样本
    out.append(
        (
            {
                "claim_type": "computational",
                "source_type": "data",
                "field_ref": ref,
                "stated_value": round(gt * 1.02, 6),
                "interpretation": "",
            },
            "FAIL",
            ["borderline"],
        )
    )
    # hedged：模糊措辞包装的准确值 → PASS；措辞不改变数值语义（点值+容差，design 默认）
    out.append(
        (
            {
                "claim_type": "computational",
                "source_type": "data",
                "field_ref": ref,
                "stated_value": round(gt, 6),
                "interpretation": f"约 {round(gt, 2)}，可能存在小幅波动",
            },
            "PASS",
            ["hedged"],
        )
    )
    return out


def _first_leaf(tree: object, path: list[str] | None = None) -> tuple[list[str], float] | None:
    path = path or []
    if isinstance(tree, dict):
        for key, value in tree.items():
            found = _first_leaf(value, [*path, str(key)])
            if found is not None:
                return found
        return None
    if isinstance(tree, list):
        for i, value in enumerate(tree):
            if isinstance(value, (int, float)) and value is not None and float(value) != 0.0:
                return [*path, str(i)], float(value)
        return None
    if isinstance(tree, (int, float)) and tree is not None and float(tree) != 0.0:
        return path, float(tree)
    return None


def generate() -> list[BenchmarkEntry]:
    state = build_state("state_v1")
    entries: list[BenchmarkEntry] = []
    n_report = 0

    def add(claim: dict, label: Label, subsets: list[str]) -> None:
        nonlocal n_report
        n_report += 1
        entries.append(
            BenchmarkEntry(
                entry_id=f"seed-{n_report:04d}",
                state_key="state_v1",
                claim=claim,
                label_final=label,
                label_a=label,
                label_b=label,
                annotator_a="synthetic-seed",
                annotator_b="synthetic-seed",
                subsets=subsets,
            )
        )

    # 每个注册根键 4 条（PASS/FAIL/borderline/hedged）
    for root in _COMPUTATIONAL_RECALC:
        for claim, label, subsets in _claims_for_root(state, root):
            add(claim, label, subsets)

    # 数值型：build_state 的 solvency_metrics 已由 calc_solvency 计算，直接读值
    debt = state["solvency_metrics"]["资产负债率"]["2024"]
    add(
        {
            "claim_type": "numerical",
            "source_type": "data",
            "field_ref": "solvency_metrics.资产负债率.2024",
            "stated_value": float(debt),
            "interpretation": "资产负债率处于适中水平",
        },
        "PASS",
        [],
    )
    add(
        {
            "claim_type": "numerical",
            "source_type": "data",
            "field_ref": "solvency_metrics.资产负债率.2024",
            "stated_value": float(debt) * 1.5,
            "interpretation": "",
        },
        "FAIL",
        [],
    )
    add(
        {
            "claim_type": "numerical",
            "source_type": "data",
            "field_ref": "solvency_metrics.资产负债率.2023",
            "stated_value": float(state["solvency_metrics"]["资产负债率"]["2023"]) * 1.03,
            "interpretation": "负债率较上年约上升",
        },
        "FAIL",
        ["borderline", "hedged"],
    )

    # llm_inference → UNVERIFIABLE
    add(
        {
            "claim_type": "numerical",
            "source_type": "llm_inference",
            "field_ref": "solvency_metrics.资产负债率.2024",
            "stated_value": 40.0,
            "interpretation": "行业惯例约 40%",
        },
        "UNVERIFIABLE",
        ["hedged"],
    )
    # 未注册根键 → UNVERIFIABLE（覆盖缺口）
    add(
        {
            "claim_type": "computational",
            "source_type": "data",
            "field_ref": "not_registered.指标.2024",
            "stated_value": 1.0,
            "interpretation": "",
        },
        "UNVERIFIABLE",
        [],
    )

    return entries


def main() -> None:
    entries = generate()
    lines = [e.model_dump_json() for e in entries]
    (_DIR / "seed.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (_DIR / "meta.json").write_text(
        json.dumps(
            {
                "version": "0.1.0-seed",
                "n_reports": len(entries),
                "n_claims": len(entries),
                "kappa": None,
                "notes": (
                    "种子集为合成确定性数据（synthetic-seed），用于准度测量管线端到端验证；"
                    "生产基准集（30-50 份历史报告 × 20-30 claim，双人背对背标注 + 仲裁，"
                    "κ 上报）在此基础上滚动补库替换——补库时追加行并递增 version。"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"生成 {len(entries)} 条 → seed.jsonl / meta.json")


if __name__ == "__main__":
    main()
