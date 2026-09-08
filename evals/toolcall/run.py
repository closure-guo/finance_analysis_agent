#!/usr/bin/env python
"""工具调用 trace 拉取（Langfuse 公共 REST API 只读客户端）。

只读约束：仅 GET /api/public/*；逐 trace 补 observations（tool_call:* span 在
observation name 上）。分页 page/limit；认证 HTTP Basic。
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import requests

LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
TRACE_NAME = os.environ.get("TOOLCALL_TRACE_NAME", "react_loop")


def _load_env() -> None:
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
    except Exception:  # noqa: BLE001, S110
        pass


def fetch_toolcall_traces(limit_pages: int = 3, page_size: int = 100) -> list[dict[str, Any]]:
    """拉取 quick 模式（react_loop）traces 并补 observations。"""
    _load_env()
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    if not (public_key and secret_key):
        raise RuntimeError("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 未配置")

    auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}"}
    traces: list[dict[str, Any]] = []
    page = 1
    while page <= limit_pages:
        params: dict[str, Any] = {"name": TRACE_NAME, "limit": page_size, "page": page}
        resp = requests.get(
            f"{LANGFUSE_HOST}/api/public/traces",
            params=params,
            headers=headers,
            timeout=40,
        )
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("data") or []
        if not rows:
            break
        traces.extend(rows)
        total_pages = (data.get("meta") or {}).get("totalPages") or 1
        if page >= total_pages:
            break
        page += 1
    for t in traces:
        try:
            detail = requests.get(
                f"{LANGFUSE_HOST}/api/public/traces/{t['id']}",
                headers=headers,
                timeout=40,
            ).json()
            t["observations"] = detail.get("observations") or []
        except Exception:  # noqa: BLE001, S110 - 单条失败不阻断整批
            t["observations"] = []
    return traces
