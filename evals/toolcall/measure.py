#!/usr/bin/env python
"""工具调用评估（add-toolcall-evaluation）：轨迹提取 + 四维质量。

数据源：Langfuse trace 的观测（name=tool_call:<工具名> span，由
agent_factory._trace_tool 埋点）——纯提取器不做任何业务调用。

四维：
- 工具选择正确性：调用名 ⊆ 合法集合（允许集）
- 参数合法性：调用 args 满足 required_by_tool（结构化样本；trace 无 args 时跳过）
- 调用效率：连续同工具名（且未换策略）判冗余
- 失败恢复：error 调用后未出现不同工具的后续调用判未恢复

用法:
    uv run python evals/toolcall/measure.py --traces path/to/traces.json [--out reports/toolcall-report.md]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

_TOOL_PREFIX = "tool_call:"

# 允许工具集（quick/deep 模式已注册的全部工具）
DEFAULT_ALLOWED_TOOLS = frozenset(
    {"web_search", "batch_web_search", "search_stock", "run_deep_analysis"}
)

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_fetch_toolcall_traces: Callable[..., list[dict[str, Any]]] | None = None
try:  # noqa: E402 - 运行时依赖可选
    from evals.toolcall.run import fetch_toolcall_traces as _fetch_toolcall_traces  # noqa: E402
except Exception:  # noqa: BLE001, S110
    _fetch_toolcall_traces = None


@dataclass
class ToolCallRecord:
    """单次工具调用（提取自观察 span）。"""

    name: str
    latency_ms: float | None = None
    error: str | None = None
    args_hint: Any = None
    timestamp: str = ""


def extract_toolcalls(trace: dict[str, Any]) -> list[ToolCallRecord]:
    """从 trace 详情（含 observations）提取工具调用序列，按发生顺序。"""
    calls: list[ToolCallRecord] = []
    for o in trace.get("observations") or []:
        name = str(o.get("name") or "")
        if not name.startswith(_TOOL_PREFIX):
            continue
        metadata = o.get("metadata") or {}
        # observation latency 单位 ms（Langfuse v3）；缺省 None
        latency = o.get("latency")
        calls.append(
            ToolCallRecord(
                name=name[len(_TOOL_PREFIX) :],
                latency_ms=float(latency) if isinstance(latency, (int, float)) else None,
                error=(metadata.get("tool_error") or None),
                args_hint=(o.get("input") or {}).get("call")
                if isinstance(o.get("input"), dict)
                else None,
                timestamp=str(trace.get("timestamp") or ""),
            )
        )
    return calls


@dataclass
class ToolcallViolations:
    allow_set: list[dict[str, Any]] = field(default_factory=list)
    params: list[dict[str, Any]] = field(default_factory=list)
    redundancy: list[dict[str, Any]] = field(default_factory=list)
    recovery: list[dict[str, Any]] = field(default_factory=list)


def allow_set_check(
    calls: list[ToolCallRecord], allowed: frozenset[str] = DEFAULT_ALLOWED_TOOLS
) -> list[dict[str, Any]]:
    """工具选择正确性：非法调用名列表（属合法集合断言，允许策略差异不算错）。"""
    return [{"name": c.name, "timestamp": c.timestamp} for c in calls if c.name not in allowed]


def validate_params(
    calls: list[ToolCallRecord], required_by_tool: dict[str, list[str]]
) -> list[dict[str, Any]]:
    """参数合法性：仅当调用带 args_hint（结构化样本路径）时校验必填键。"""
    violations: list[dict[str, Any]] = []
    for c in calls:
        if c.args_hint is None:
            continue  # trace 无 args 时跳过（数据源限制，不误判）
        required = required_by_tool.get(c.name, [])
        hint = c.args_hint if isinstance(c.args_hint, dict) else {}
        missing = [k for k in required if k not in hint]
        if missing:
            violations.append({"name": c.name, "missing": missing, "args": hint})
    return violations


def efficiency_issues(calls: list[ToolCallRecord]) -> list[dict[str, Any]]:
    """调用效率：同一工具名连续调用（未换策略）判冗余一次。"""
    issues: list[dict[str, Any]] = []
    prev: str | None = None
    for idx, c in enumerate(calls):
        if prev is not None and c.name == prev:
            issues.append({"index": idx, "name": c.name, "note": "连续重复调用未换策略"})
        prev = c.name
    return issues


def failure_recovery(calls: list[ToolCallRecord]) -> list[dict[str, Any]]:
    """失败恢复：error 调用后须有后续调用（且工具不同）；否则判未恢复。"""
    unrecovered: list[dict[str, Any]] = []
    for idx, c in enumerate(calls):
        if c.error is None:
            continue
        rest = calls[idx + 1 :]
        recovered = any(nc.name != c.name for nc in rest)
        if not recovered:
            unrecovered.append({"index": idx, "name": c.name, "error": c.error})
    return unrecovered


@dataclass
class ToolcallReport:
    total_calls: int = 0
    per_tool: dict[str, int] = field(default_factory=dict)
    violations: ToolcallViolations = field(default_factory=ToolcallViolations)


def evaluate(
    traces: list[dict[str, Any]],
    allowed: frozenset[str] = DEFAULT_ALLOWED_TOOLS,
    required_by_tool: dict[str, list[str]] | None = None,
) -> tuple[ToolcallReport, list[list[ToolCallRecord]]]:
    """批量评估：返回报告 + 每 trace 的调用序列。"""
    required = required_by_tool or {}
    report = ToolcallReport()
    sequences: list[list[ToolCallRecord]] = []
    for t in traces:
        calls = extract_toolcalls(t)
        sequences.append(calls)
        report.total_calls += len(calls)
        for c in calls:
            report.per_tool[c.name] = report.per_tool.get(c.name, 0) + 1
        report.violations.allow_set.extend(allow_set_check(calls, allowed))
        report.violations.params.extend(validate_params(calls, required))
        report.violations.redundancy.extend(efficiency_issues(calls))
        report.violations.recovery.extend(failure_recovery(calls))
    return report, sequences


def render_report(report: ToolcallReport) -> str:
    dist = "、".join(f"{k} {v}" for k, v in sorted(report.per_tool.items())) or "无"
    lines = [
        "# 工具调用评估报告",
        "",
        f"- 生成时间: {datetime.now().isoformat(timespec='seconds')}",
        f"- 调用总数: {report.total_calls}（{dist}）",
        "",
        "## 工具选择（合法集合断言）",
        "",
        f"- 非法工具名: {len(report.violations.allow_set)}",
    ]
    for v in report.violations.allow_set[:10]:
        lines.append(f"  - {v['name']} @ {v['timestamp'][:19]}")
    lines += [
        "",
        "## 参数合法性",
        "",
        f"- 缺必填参数调用: {len(report.violations.params)}",
    ]
    for v in report.violations.params[:10]:
        lines.append(f"  - {v['name']} 缺 {v['missing']}")
    lines += [
        "",
        "## 调用效率（冗余检测）",
        "",
        f"- 连续重复: {len(report.violations.redundancy)}",
    ]
    for v in report.violations.redundancy[:10]:
        lines.append(f"  - #{v['index']} {v['name']}: {v['note']}")
    lines += [
        "",
        "## 失败恢复",
        "",
        f"- 未恢复失败: {len(report.violations.recovery)}",
    ]
    for v in report.violations.recovery[:10]:
        lines.append(f"  - #{v['index']} {v['name']}: {v['error'][:120]}")
    lines += [
        "",
        "> 门禁：金标样本（fixtures）上四维违例须为 0；本报告为生产流量监控（趋势防漂移）。",
        "",
    ]
    return "\n".join(lines)


def run_offline(
    traces: list[dict[str, Any]],
    allowed: frozenset[str] = DEFAULT_ALLOWED_TOOLS,
    required_by_tool: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    report, sequences = evaluate(traces, allowed, required_by_tool)
    return {"report": report, "sequences": sequences}


def main() -> None:
    parser = argparse.ArgumentParser(description="工具调用评估")
    parser.add_argument("--traces", type=Path, required=False)
    parser.add_argument("--out", type=Path, default=Path("reports/toolcall-report.md"))
    args = parser.parse_args()

    if args.traces:
        traces = json.loads(args.traces.read_text(encoding="utf-8"))
    elif _fetch_toolcall_traces is not None:
        traces = _fetch_toolcall_traces()
    else:
        parser.error("未提供 --traces 且 run 模块不可导入")

    report, _ = evaluate(traces)
    text = render_report(report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
