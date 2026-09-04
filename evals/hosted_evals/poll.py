#!/usr/bin/env python
"""hosted evaluator 降级轮询（enable-hosted-evaluator 降级方案）。

取证（2026-09-04）：自托管 Langfuse 3.205.1 无 evaluator 公共 API
（/api/public/eval-configs 返回 SPA HTML）→ managed evaluator 无法脚本化
配置/版本化。按 spec 预设降级：轮询 /api/public/scores（UI evaluator 产出的
分数带 configId）做在线质量监控 + 告警 + 口径对齐（hosted vs 离线 judge 同
trace 打分比对）。

evaluator 模板治理：UI 配置的模板以快照归档 docs/evals/hosted-evaluator-template.md
（变更手工回填，等效版本管理）。

用法:
    uv run python evals/hosted_evals/poll.py [--config-id ID] [--out reports/hosted-eval-report.md]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import statistics
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
ALERT_THRESHOLD = float(os.getenv("HOSTED_EVAL_ALERT_THRESHOLD", "3.5"))  # 均分跌破告警
WINDOW_HOURS = int(os.getenv("HOSTED_EVAL_WINDOW_HOURS", "24"))
LOW_SAMPLE_TOP_N = 10

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@dataclass
class ScoreRecord:
    score_id: str
    name: str
    value: float
    trace_id: str
    config_id: str | None
    created_at: str


@dataclass
class WindowAggregate:
    total: int = 0
    avg: float | None = None
    low_count: int = 0
    low_traces: list[dict[str, Any]] = field(default_factory=list)
    alert: bool = False


def _auth() -> tuple[str, str, str]:
    env_path = _ROOT / ".env"
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
    except Exception:  # noqa: BLE001, S110
        pass
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    if not (public_key and secret_key):
        raise RuntimeError("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 未配置")
    return base64.b64encode(f"{public_key}:{secret_key}".encode()).decode(), public_key, secret_key


def fetch_scores(
    config_id: str | None = None,
    name: str | None = None,
    limit_pages: int = 3,
    page_size: int = 100,
) -> list[ScoreRecord]:
    """拉取窗口内分数；UI evaluator 分数带 configId，API 分数 configId=null。"""
    auth, _, _ = _auth()
    cutoff = (datetime.now(UTC) - timedelta(hours=WINDOW_HOURS)).isoformat()
    records: list[ScoreRecord] = []
    page = 1
    while page <= limit_pages:
        params: dict[str, Any] = {"limit": page_size, "page": page, "fromTimestamp": cutoff}
        if config_id:
            params["configId"] = config_id
        if name:
            params["name"] = name
        resp = requests.get(
            f"{LANGFUSE_HOST}/api/public/scores",
            params=params,
            headers={"Authorization": f"Basic {auth}"},
            timeout=40,
        )
        resp.raise_for_status()
        rows = resp.json().get("data") or []
        if not rows:
            break
        for r in rows:
            v = r.get("value")
            if not isinstance(v, (int, float)):
                continue
            records.append(
                ScoreRecord(
                    score_id=str(r.get("id") or ""),
                    name=str(r.get("name") or ""),
                    value=float(v),
                    trace_id=str(r.get("traceId") or ""),
                    config_id=r.get("configId"),
                    created_at=str(r.get("createdAt") or ""),
                )
            )
        total_pages = (resp.json().get("meta") or {}).get("totalPages") or 1
        if page >= total_pages:
            break
        page += 1
    return records


def aggregate_window(
    scores: list[ScoreRecord], alert_threshold: float = ALERT_THRESHOLD
) -> WindowAggregate:
    """滑动窗口聚合：均分 + 低分 trace 清单 + 阈值告警。"""
    agg = WindowAggregate(total=len(scores))
    if not scores:
        return agg
    agg.avg = round(statistics.mean(s.value for s in scores), 4)
    lows = [s for s in scores if s.value < alert_threshold]
    agg.low_count = len(lows)
    agg.low_traces = [
        {"score_id": s.score_id, "trace_id": s.trace_id, "name": s.name, "value": s.value}
        for s in lows[:LOW_SAMPLE_TOP_N]
    ]
    agg.alert = agg.avg < alert_threshold
    return agg


def align_offline(
    hosted: list[ScoreRecord],
    offline_by_trace: dict[str, float],
    max_mae: float = 1.0,
) -> dict[str, Any]:
    """口径对齐：同 trace 的 hosted 分 vs 离线 judge 分，MAE 超阈值标口径漂移。"""
    pairs: list[dict[str, Any]] = []
    for s in hosted:
        off = offline_by_trace.get(s.trace_id)
        if off is None:
            continue
        pairs.append({"trace_id": s.trace_id, "hosted": s.value, "offline": off})
    mae = None
    drift = False
    if pairs:
        mae = round(statistics.mean(abs(p["hosted"] - p["offline"]) for p in pairs), 4)
        drift = mae > max_mae
    return {"pairs": pairs, "mae": mae, "drift": drift, "max_mae": max_mae}


def render_report(agg: WindowAggregate, align: dict[str, Any]) -> str:
    lines = [
        "# hosted evaluator 在线评估监控（降级轮询）",
        "",
        f"- 生成时间: {datetime.now().isoformat(timespec='seconds')}",
        f"- 窗口: 近 {WINDOW_HOURS}h，分数 {agg.total} 条",
        f"- 均分: {agg.avg if agg.avg is not None else '—'}（阈值 {ALERT_THRESHOLD}）",
        f"- 告警: {'⚠️ 均分跌破阈值' if agg.alert else '否'}",
        f"- 低分条目: {agg.low_count}",
    ]
    for t in agg.low_traces:
        lines.append(f"  - {t['name']} {t['value']} trace={t['trace_id'][:10]}")
    lines += [
        "",
        "## 口径对齐（hosted vs 离线 judge）",
        "",
        f"- 配对样本: {len(align['pairs'])} | MAE: {align['mae'] if align['mae'] is not None else '—'} | "
        f"漂移: {'⚠️ 是' if align['drift'] else '否'}（阈值 MAE≤{align['max_mae']}）",
        "",
        "> 自托管 3.205.1 无 evaluator 公共 API：evaluator 在 UI 配置，模板快照归档",
        "> docs/evals/hosted-evaluator-template.md（变更手工回填）。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="hosted evaluator 降级轮询")
    parser.add_argument("--config-id", type=str, default=None, help="UI evaluator 的 configId")
    parser.add_argument("--name", type=str, default=None, help="按分数名过滤")
    parser.add_argument("--out", type=Path, default=Path("reports/hosted-eval-report.md"))
    args = parser.parse_args()

    scores = fetch_scores(config_id=args.config_id, name=args.name)
    agg = aggregate_window(scores)
    text = render_report(agg, align_offline(scores, {}))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()


def _dump_scores(scores: list[ScoreRecord]) -> str:
    return json.dumps([s.__dict__ for s in scores], ensure_ascii=False)
