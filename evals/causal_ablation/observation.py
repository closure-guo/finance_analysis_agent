"""常规观测电池（delta add-causal-observation-battery）。

固定 P1 快照（20 标的）× 当前生产栈（prompt/模型）→ 三个已校准读数：
grounding 无源断言率 / B1 风险点吸收率 / B2 交锋修正率。

**观测不裁决**：无两臂对照，不产出任何层间结论句（层归因走因果消融实验批）；
读数定位为跨轮趋势对照（与上轮对照、人工解读）。

判定实现全部复用既有库侧函数（bear_grounding / family_b_text / family_b_judge /
family_b_materials），本模块只是薄驱动：digest 核验 → 材料腿 → 三判定 → 汇总落盘。
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from evals.causal_ablation import bear_grounding as bg
from evals.causal_ablation import family_b_judge as fj
from evals.causal_ablation import family_b_materials as fb
from evals.causal_ablation import family_b_text as ft
from evals.causal_ablation import pilot_runner as pr
from evals.causal_ablation.family_b_materials import (
    run_materials,  # noqa: F401 - 模块级名（digest 测试 monkeypatch 面）
)

# P1 固定快照的 20 标的（与 P2 材料批同源；跨轮可比的分母）
TICKERS: tuple[str, ...] = (
    "600519",
    "000001",
    "002415",
    "300750",
    "601318",
    "002594",
    "600036",
    "000858",
    "601899",
    "002304",
    "601398",
    "600030",
    "000333",
    "002352",
    "601012",
    "600887",
    "000651",
    "600276",
    "601888",
    "002027",
)
DEFAULT_SNAPSHOT_DIR = Path("reports/ablation/p1/materials")
DEFAULT_OUT_DIR = Path("reports/ablation/observation")
RUNS_JSONL = Path("docs/evals/metrics/runs.jsonl")

# 全量判定口径（观测轮对齐 09-20 观测批：不用每标的闸门，闸门是实验批的成本旋钮）
_FULL_JUDGMENT_GATE = 10_000

# 校准记录注册表：rubric → 最近一次过 0.80 校准门的证据（owner 收口时更新）。
# 读数落盘时按判定行携带的 rubric 查表；查不到 → provisional（不得与历史轮直接对照）。
CALIBRATION_REGISTRY: dict[str, dict] = {
    "b1-v1": {
        "agreement": 0.875,
        "rows": 40,
        "closed": "2026-09-20",
        "source": "metrics.md §19.2/§19.13",
    },
    "b2-v1": {"agreement": 0.906, "rows": 32, "closed": "2026-09-18", "source": "metrics.md §19.2"},
    "bg-v1": {"agreement": 1.000, "rows": 14, "closed": "2026-09-18", "source": "metrics.md §19.5"},
}
_DEFAULT_RUBRIC = {
    "b1_absorption": fj.B1_RUBRIC,
    "b2_correction": fj.B2_RUBRIC,
    "grounding": bg.BG_RUBRIC,
}


class SnapshotDriftError(RuntimeError):
    """快照 digest 与登记值不一致：显式失败，禁止静默混轮比较。"""


def snapshot_digests(snapshot_dir: Path, tickers: Sequence[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for ticker in tickers:
        product = pr.load_product(pr.product_path(Path(snapshot_dir), ticker))
        out[ticker] = str(product.get("snapshot_digest") or "")
    return out


def verify_snapshot_digests(actual: dict[str, str], expected: dict[str, str]) -> None:
    drift = [
        f"{t}: 登记值={expected[t]!r} vs 本次={actual.get(t)!r}"
        for t in expected
        if actual.get(t) != expected[t]
    ]
    if drift:
        raise SnapshotDriftError("快照 digest 与登记值不一致（禁止混轮比较）: " + "; ".join(drift))


def _rate_from_labels(rows: Sequence[dict]) -> float | None:
    labeled = [r for r in rows if r.get("judge_label") is not None]
    if not labeled:
        return None
    return round(sum(1 for r in labeled if r["judge_label"] is True) / len(labeled), 4)


def _reading(
    name: str,
    rows: Sequence[dict],
    *,
    registry: dict[str, dict],
    report: dict | None = None,
) -> dict:
    """读数行：率 + 分母 + 解析失败数 + rubric + provisional 派生。"""
    rubric = next((str(r.get("rubric")) for r in rows if r.get("rubric")), _DEFAULT_RUBRIC[name])
    rate = report["rate"] if report is not None else _rate_from_labels(rows)
    base = {
        "rate": rate,
        "rows": report["rows"] if report is not None else len(rows),
        "parse_failed": (
            report["parse_failed"]
            if report is not None
            else sum(1 for r in rows if r.get("judge_parse_failed"))
        ),
        "rubric": rubric,
        "provisional": rubric not in registry,
    }
    if report is not None:
        base["labeled"] = report.get("labeled")
        base["unsupported_count"] = report.get("unsupported_count")
    else:
        base["positive"] = sum(1 for r in rows if r.get("judge_label") is True)
    return base


def run_battery(
    tickers: Sequence[str],
    *,
    snapshot_dir: Path | str = DEFAULT_SNAPSHOT_DIR,
    out_dir: Path | str = DEFAULT_OUT_DIR,
    expected_digests: dict[str, str] | None = None,
    graph_runner: Callable[..., dict] | None = None,
    llm_meter: Callable[[], int] | None = None,
    judge_fn: Callable[[str], str] | None = None,
    registry: dict[str, dict] | None = None,
) -> dict:
    """跑一轮观测电池（材料腿 + 三判定），返回汇总 dict。

    graph_runner / llm_meter / judge_fn 可注入（测试零 LLM）；缺省为生产实现。
    expected_digests 提供时逐标的核验（不一致抛 SnapshotDriftError，不烧 token）。
    """
    snapshot_dir = Path(snapshot_dir)
    out_dir = Path(out_dir)
    reg = CALIBRATION_REGISTRY if registry is None else registry

    digests = snapshot_digests(snapshot_dir, tickers)
    if expected_digests:
        verify_snapshot_digests(digests, expected_digests)

    # ── 材料腿（固定快照 × 当前生产栈；已有材料跳过，续跑不重烧 token）──
    units = run_materials(
        list(tickers),
        snapshot_materials_dir=snapshot_dir,
        out_dir=out_dir,
        graph_runner=graph_runner or pr.default_graph_runner,
        llm_meter=llm_meter,
    )
    materials_calls_vals = [u.get("llm_calls") for u in units]
    materials_calls = (
        sum(v for v in materials_calls_vals if v is not None)
        if any(v is not None for v in materials_calls_vals)
        else None
    )
    states = {t: fb.load_material(out_dir, t)["state"] for t in tickers}

    # ── 判定腿（judge_fn 计数包装：判定调用数分腿申报）──
    counter = {"n": 0}

    def _counting_fn(prompt: str) -> str:
        counter["n"] += 1
        return (judge_fn or fj.default_judge_fn())(prompt)

    # grounding：宇宙 = 第 1 轮 ∧ kind=data 空方论点（对 bear 实际输入判可支撑性）
    bg_rows: list[dict] = []
    for t in tickers:
        bg_rows.extend(bg.grounding_units(t, states[t]))
    bg_judged = bg.run_grounding(bg_rows, llm_fn=_counting_fn)
    grounding = _reading(
        "grounding", bg_judged, registry=reg, report=bg.grounding_report(bg_judged)
    )

    # B1：辩论新增风险点 → 是否被决策吸收（全量判定口径）
    b1_rows = ft.judge_material_rows(
        [{"ticker": t, "_state": states[t], "b1": ft.b1_unit(states[t])} for t in tickers]
    )
    refs = {t: ft.analyst_reference_points(states[t]) for t in tickers}
    for row in b1_rows:
        row["reference_points"] = refs[str(row.get("ticker") or "")]
    b1_judged = fj.run_b1_judgments(b1_rows, llm_fn=_counting_fn, per_ticker=_FULL_JUDGMENT_GATE)
    b1 = _reading("b1_absorption", b1_judged, registry=reg)

    # B2：交锋修正（rebuttal_to 锚定的观点是否真被修正）
    b2_rows = ft.b2_material_rows(
        [{"ticker": t, "_state": states[t], "b2": ft.b2_unit(states[t])} for t in tickers]
    )
    b2_judged = fj.run_b2_judgments(b2_rows, llm_fn=_counting_fn, per_ticker=_FULL_JUDGMENT_GATE)
    b2 = _reading("b2_correction", b2_judged, registry=reg)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "tickers": list(tickers),
        "snapshot_digests": digests,
        "readings": {"grounding": grounding, "b1_absorption": b1, "b2_correction": b2},
        "llm_calls": {"materials": materials_calls, "judgments": counter["n"]},
        "out_dir": str(out_dir),
    }


def runs_jsonl_line(result: dict, *, started_at: str, git_head: str, notes: str = "") -> str:
    """观测轮 → runs.jsonl 单行（收口时追加；含 llm_calls 分腿申报）。"""
    payload = {
        "run": f"causal-observation-{started_at[:10]}",
        "started_at": started_at,
        "git_head": git_head,
        "notes": notes or "常规观测电池（delta add-causal-observation-battery）",
        "means": {
            "grounding_unsupported_rate": result["readings"]["grounding"]["rate"],
            "b1_absorbed_rate": result["readings"]["b1_absorption"]["rate"],
            "b2_corrected_rate": result["readings"]["b2_correction"]["rate"],
            "llm_calls": result["llm_calls"],
        },
        "report": str(result.get("out_dir")) + "（本地）",
    }
    return json.dumps(payload, ensure_ascii=False)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="常规观测电池（grounding/B1/B2 三读数）")
    parser.add_argument("--snapshot-dir", type=Path, default=DEFAULT_SNAPSHOT_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--tickers", nargs="+", default=list(TICKERS))
    parser.add_argument(
        "--expected-digests-file",
        type=Path,
        default=None,
        help="上一轮登记的快照 digest JSON（不提供则本轮作为基线登记，不核验）",
    )
    parser.add_argument(
        "--append-runs-jsonl",
        action="store_true",
        help="把本轮 runs.jsonl 行追加进台账（默认只打印，收口确认后手动追加）",
    )
    return parser.parse_args(argv)


def _git_head() -> str:
    import shutil
    import subprocess

    git = shutil.which("git")
    if not git:
        return ""
    try:
        return subprocess.run(  # noqa: S603 - 完整路径 + 固定 argv 的 git 只读查询
            [git, "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except Exception:  # noqa: BLE001 - git 不可用时留空，收口时人工补
        return ""


def _install_cost_meter() -> Callable[[], int] | None:
    """usage meter 接线（材料腿调用数申报）；不可用时如实记 None（沿 p2 脚本同款降级）。"""
    import sys

    scripts_dir = str(Path(__file__).resolve().parents[2] / "tests" / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    try:
        import backtest_pilot_2023 as pilot_util
        import p1_injection_pilot as pilot_cli

        if pilot_cli._install_cost_meter() is None:
            return None
    except Exception as exc:  # noqa: BLE001 - 计量不可用不阻断观测
        print(
            f"[警告] usage meter 未接线（{type(exc).__name__}: {exc}）：材料腿调用数记 unknown",
            flush=True,
        )
        return None
    return lambda: len(pilot_util._usage_ledger)


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    args = parse_args()
    expected = (
        json.loads(args.expected_digests_file.read_text(encoding="utf-8"))
        if args.expected_digests_file
        else None
    )
    result = run_battery(
        args.tickers,
        snapshot_dir=args.snapshot_dir,
        out_dir=args.out_dir,
        expected_digests=expected,
        llm_meter=_install_cost_meter(),
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    (args.out_dir / f"observation-{ts}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.out_dir / "snapshot-digests.json").write_text(
        json.dumps(result["snapshot_digests"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    started_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    line = runs_jsonl_line(result, started_at=started_at, git_head=_git_head())
    print(line, flush=True)
    if args.append_runs_jsonl:
        with RUNS_JSONL.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        print(f"[台账] 已追加 → {RUNS_JSONL}", flush=True)


if __name__ == "__main__":
    main()
