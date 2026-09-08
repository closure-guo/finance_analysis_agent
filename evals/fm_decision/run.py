#!/usr/bin/env python
"""FM 决策 trace 拉取（Langfuse 公共 REST API 只读客户端）。

只读约束（任务红线）：仅 GET /api/public/*，零写入。
分页 page/limit，认证 HTTP Basic（public_key, secret_key）。
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import requests

LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")


def _load_env() -> None:
    """独立运行时加载 .env（不依赖外部 shell 导入）。"""
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
    except Exception:  # noqa: BLE001, S110 - dotenv 缺失时跳过
        pass


def fetch_fund_manager_traces(limit_pages: int = 6, page_size: int = 100) -> list[dict[str, Any]]:
    """拉取 name=fund_manager 的 trace 列表（output.answer 含决策 JSON）。

    分页遍历；Langfuse 不可用抛错（分布统计必须拿到真实数据，不做静默降级）。
    """
    _load_env()
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    if not (public_key and secret_key):
        raise RuntimeError("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 未配置")

    auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    traces: list[dict[str, Any]] = []
    page = 1
    while page <= limit_pages:
        params: dict[str, Any] = {"name": "fund_manager", "limit": page_size, "page": page}
        resp = requests.get(
            f"{LANGFUSE_HOST}/api/public/traces",
            params=params,
            headers={"Authorization": f"Basic {auth}"},
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
    return traces
