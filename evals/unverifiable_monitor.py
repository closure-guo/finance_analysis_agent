"""citation_unverifiable_ratio 突升监控（spec citation-verification「UNVERIFIABLE 占比监控」）。

占比突升 = 数据层退化先行信号（数据源接口变更/事件管线降级/注册表覆盖缺口扩大）。
纯逻辑（detect_rise / evaluate_history）可测；CLI 从 Langfuse 拉取 Score 序列检测。
"""

from __future__ import annotations

import base64
import json
import os
import urllib.request
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

SCORE_NAME = "citation_unverifiable_ratio"
DEFAULT_BASELINE_WINDOW = 30
DEFAULT_RECENT_WINDOW = 5
DEFAULT_THRESHOLD_PP = 0.10  # +10pp


def detect_rise(
    recent: Sequence[float],
    baseline: Sequence[float],
    threshold_pp: float = DEFAULT_THRESHOLD_PP,
) -> dict | None:
    """recent 均值较 baseline 均值上升超过 threshold_pp → 告警 dict；否则 None。"""
    if not recent or not baseline:
        return None
    recent_mean = sum(recent) / len(recent)
    baseline_mean = sum(baseline) / len(baseline)
    rise_pp = recent_mean - baseline_mean
    if rise_pp <= threshold_pp:
        return None
    return {
        "level": "warning",
        "score": SCORE_NAME,
        "recent_mean": round(recent_mean, 4),
        "baseline_mean": round(baseline_mean, 4),
        "rise_pp": round(rise_pp, 4),
        "threshold_pp": threshold_pp,
        "hint": "排查数据层（数据源接口/事件管线）或 citation 注册表覆盖缺口",
    }


def evaluate_history(
    history: list[tuple[str, float]],
    *,
    baseline_window: int = DEFAULT_BASELINE_WINDOW,
    recent_window: int = DEFAULT_RECENT_WINDOW,
    threshold_pp: float = DEFAULT_THRESHOLD_PP,
) -> dict | None:
    """history: [(timestamp, ratio)]，按时间升序取 recent_window 为近期、
    其前 baseline_window 为基线，做突升检测。样本不足返回 None。"""
    ordered = sorted(history, key=lambda t: t[0])
    if len(ordered) < recent_window + baseline_window:
        return None
    recent = [v for _, v in ordered[-recent_window:]]
    baseline = [v for _, v in ordered[-(recent_window + baseline_window) : -recent_window]]
    return detect_rise(recent, baseline, threshold_pp)


def fetch_scores(host: str, limit: int = 200) -> list[tuple[str, float]]:
    """从 Langfuse REST API 拉取该 Score 最近记录（timestamp, value），升序返回。"""
    public = os.environ["LANGFUSE_PUBLIC_KEY"]
    secret = os.environ["LANGFUSE_SECRET_KEY"]
    token = base64.b64encode(f"{public}:{secret}".encode()).decode()
    url = f"{host.rstrip('/')}/api/public/scores?name={SCORE_NAME}&limit={limit}"
    req = urllib.request.Request(  # noqa: S310 - 内网 Langfuse
        url, headers={"Authorization": f"Basic {token}"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - 内网 Langfuse
        data = json.loads(resp.read().decode())
    rows = [(item["timestamp"], float(item["value"])) for item in data.get("data", [])]
    return sorted(rows, key=lambda t: t[0])


def main() -> None:
    load_dotenv()
    host = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
    history = fetch_scores(host)
    alert = evaluate_history(history)
    record = {
        "checked_at": datetime.now(UTC).isoformat(),
        "score": SCORE_NAME,
        "n_scores": len(history),
        "alert": alert,
    }
    out_dir = Path("reports/monitoring")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"unverifiable-ratio-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False))
    print(f"监控记录已写入 {path}")


if __name__ == "__main__":
    main()
