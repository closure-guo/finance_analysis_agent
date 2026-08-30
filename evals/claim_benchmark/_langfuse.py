"""Langfuse v3 公共 REST API 只读客户端（harvest/verify 共用）。

只读约束（任务红线）：本模块仅 GET /api/public/*，对业务库零写入；
Langfuse 不可用时显式抛错（harvest 必须拿到真实数据，不做静默降级）。

v3 公共 API 要点：
- traces 列表响应已含完整 metadata（citation_report 在其中）与 input/output，
  收割无需逐 trace 拉详情；
- 分页为 page/limit，响应 meta.totalItems / totalPages；
- 认证 = HTTP Basic（public_key, secret_key）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import requests

LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
FIX_CUTOFF_DEFAULT = "2026-08-29T04:05:00+00:00"  # 修正契约合入（bd25a5b 提交时间）


def _load_env(env_path: Path | None = None) -> None:
    """harvest 独立运行时加载 .env（避免依赖外部 shell 导入）。"""
    if env_path is None:
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
    except Exception:  # noqa: BLE001, S110 - dotenv 缺失时跳过，环境变量已在 shell 提供
        pass


@dataclass
class ClaimRecord:
    """单条收割记录（claims_raw.jsonl 的一行）。"""

    claim: dict
    verifier_status: str
    ground_truth: object | None
    delta: object | None
    coverage_gap: bool
    trace_id: str
    stock_code: str
    stock_name: str
    trace_timestamp: str
    trace_version: str  # pre_fix | post_fix
    rejudged_status: str

    def to_dict(self) -> dict:
        return {
            "claim": self.claim,
            "verifier_status": self.verifier_status,
            "ground_truth": self.ground_truth,
            "delta": self.delta,
            "coverage_gap": self.coverage_gap,
            "trace_id": self.trace_id,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "trace_timestamp": self.trace_timestamp,
            "trace_version": self.trace_version,
            "rejudged_status": self.rejudged_status,
        }


class LangfuseClient:
    """只读 Langfuse 客户端：分页拉取 deep_analysis trace 的 citation_report。"""

    def __init__(self, host: str | None = None) -> None:
        self.host = (host or LANGFUSE_HOST).rstrip("/")
        pk = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
        sk = os.environ.get("LANGFUSE_SECRET_KEY", "")
        if not pk or not sk:
            raise RuntimeError("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 未配置")
        self.auth = (pk, sk)

    def iter_deep_traces(self, from_date: datetime, to_date: datetime | None = None) -> list[dict]:
        """拉取 [from_date, to_date] 区间内带 citation_report 的 deep_analysis trace。

        name 前缀过滤在客户端完成（v3 API 的 name 参数为精确匹配）。
        """
        traces: list[dict] = []
        page = 1
        while True:
            r = requests.get(
                f"{self.host}/api/public/traces",
                params={"limit": 100, "page": page},
                auth=self.auth,
                timeout=30,
            )
            r.raise_for_status()
            d = r.json()
            meta = d.get("meta") or {}
            for t in d.get("data") or []:
                name = str(t.get("name") or "")
                ts = t.get("timestamp")
                if not name.startswith("deep_analysis:") or not ts:
                    continue
                try:
                    ts_dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                except ValueError:
                    continue
                if ts_dt < from_date:
                    continue
                if to_date is not None and ts_dt > to_date:
                    continue
                md = t.get("metadata") or {}
                if isinstance(md, dict) and md.get("citation_report"):
                    traces.append(t)
            if page >= (meta.get("totalPages") or 1):
                break
            page += 1
        traces.sort(key=lambda t: t.get("timestamp") or "")
        return traces

    @staticmethod
    def extract_report(trace: dict) -> dict:
        md = trace.get("metadata") or {}
        report = md.get("citation_report")
        if not isinstance(report, dict):
            raise ValueError(f"trace {trace.get('id')} 缺 citation_report")
        return report


def parse_cutoff(value: str) -> datetime:
    """解析 --fix-cutoff；缺省用 FIX_CUTOFF_DEFAULT。"""
    raw = value or FIX_CUTOFF_DEFAULT
    ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts


def stock_code_from_trace(trace: dict) -> str:
    """stock_code 优先取 trace input.stock_code，缺省回退 trace 名后缀。"""
    inp = trace.get("input") or {}
    if isinstance(inp, dict) and inp.get("stock_code"):
        return str(inp["stock_code"])
    return str((trace.get("name") or "").split(":")[-1])
