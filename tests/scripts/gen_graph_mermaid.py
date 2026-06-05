"""从 LangGraph 运行时 + 路由函数生成完整 Mermaid 图（含条件边）

输出:
  - docs/assets/graph.mmd   Mermaid 源码
  - docs/assets/graph.png   渲染后的 PNG（依赖 mermaid.ink）
"""

import base64
import sys
import urllib.request
from pathlib import Path

from finance_agent.routing import after_agent, after_check_cache, after_validate, route_to_agent

# ── 路由函数 → 所有可能目标 ──────────────────────────────────────────

# after_check_cache: MISS → fetch_data, HIT → validate_financials
CACHE_EDGES = {
    "check_cache": [
        (after_check_cache({"cache_result": "MISS"}), "MISS 首次"),
        (after_check_cache({"cache_result": "HIT"}), "HIT 报表已有"),
    ]
}

# after_validate: FAIL → END, PASS → compute_metrics
VALIDATE_EDGES = {
    "validate_financials": [
        (after_validate({"validation_result": "FAIL"}), "FAIL ✗"),
        (after_validate({"validation_result": "PASS"}), "PASS ✓"),
    ]
}

# route_to_agent: 每种 analysis_type 派发到哪些 agent
AGENT_EDGES = {
    "compute_metrics": [
        (send.node, label)
        for atype in ("financial", "investment", "comprehensive")
        for send in route_to_agent({"analysis_type": atype})
        for label in [
            {
                "financial": "financial",
                "investment": "investment",
                "comprehensive": "comprehensive 并行",
            }[atype]
        ]
    ]
}

# after_agent: comprehensive → merge, single → generate_file
POST_AGENT_EDGES = {}
for agent in ("fa_analyze", "ia_analyze"):
    targets = set()
    for atype in ("financial", "investment", "comprehensive"):
        t = after_agent({"analysis_type": atype})
        label = "comprehensive" if atype == "comprehensive" else "单 Agent"
        targets.add((t, label))
    POST_AGENT_EDGES[agent] = list(targets)


def _dedup(edges: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """合并重复 (source, target) 的标签"""
    grouped: dict[str, list[str]] = {}
    for target, label in edges:
        grouped.setdefault(target, []).append(label)

    return [(t, " / ".join(dict.fromkeys(ls))) for t, ls in grouped.items()]


def generate_mermaid() -> str:
    lines = [
        "flowchart TD",
        "",
        "    START([START]) --> check_cache",
        "",
        "    subgraph PREP[数据准备]",
        '        check_cache["① check_cache<br/>查缓存"]',
        '        fetch_data["② fetch_data<br/>AKShare 拉取"]',
        '        validate_financials["③ validate_financials<br/>勾稽校验"]',
        '        compute_metrics["④ compute_metrics<br/>指标计算"]',
        "    end",
        "",
        '    Route{"route_to_agent"}',
        '    fa_analyze["⑤ fa_analyze<br/>财务分析"]',
        '    ia_analyze["⑥ ia_analyze<br/>投资分析"]',
        '    merge["⑦ merge<br/>合并报告"]',
        '    generate_file["⑧ generate_file<br/>文件导出"]',
        "    END([END])",
        "    END_ERR([终止: 校验失败])",
        "",
        "    %% 静态边",
        "    fetch_data --> validate_financials",
        "    merge --> generate_file",
        "    generate_file --> END",
        "",
        "    %% 条件边 — 数据准备",
    ]

    # check_cache 条件边
    for target, label in _dedup(CACHE_EDGES["check_cache"]):
        lines.append(f'    check_cache -->|"{label}"| {target}')

    # validate 条件边
    for target, label in VALIDATE_EDGES["validate_financials"]:
        tgt = "END_ERR" if target == "__end__" else target
        lines.append(f'    validate_financials -->|"{label}"| {tgt}')

    lines.append("")
    lines.append("    %% 条件边 — Agent 路由")

    # compute_metrics → agents
    for target, label in _dedup(AGENT_EDGES["compute_metrics"]):
        lines.append(f'    compute_metrics -->|"{label}"| {target}')

    lines.append("")
    lines.append("    %% 条件边 — Agent 后处理")

    # agent → merge/generate_file
    for agent, edges in POST_AGENT_EDGES.items():
        for target, label in edges:
            tgt = target
            lines.append(f'    {agent} -->|"{label}"| {tgt}')

    # 样式
    lines.extend(
        [
            "",
            "    style PREP fill:#e8f5e9",
            "    style Route fill:#ff9800,color:#fff",
            "    style fa_analyze fill:#e3f2fd",
            "    style ia_analyze fill:#f3e5f5",
            "    style merge fill:#ab47bc,color:#fff",
            "    style generate_file fill:#ef9a9a",
            "    style END_ERR fill:#ef5350,color:#fff",
        ]
    )

    return "\n".join(lines)


def render_png(mermaid: str, output: Path) -> bool:
    """用 mermaid.ink 渲染 PNG"""
    try:
        encoded = base64.urlsafe_b64encode(mermaid.encode()).decode()
        url = f"https://mermaid.ink/img/{encoded}?type=png"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})  # noqa: S310
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            data = resp.read()
        if len(data) < 500:
            print(f"  ⚠ mermaid.ink 返回异常 ({len(data)} bytes)", file=sys.stderr)
            return False
        output.write_bytes(data)
        print(f"  ✓ PNG ({len(data):,} bytes) → {output}", file=sys.stderr)
        return True
    except Exception as e:
        print(f"  ✗ PNG 渲染失败: {e}", file=sys.stderr)
        return False


def main() -> None:
    root = Path(__file__).resolve().parent.parent.parent
    assets = root / "docs" / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    mermaid = generate_mermaid()

    mmd_path = assets / "graph.mmd"
    mmd_path.write_text(mermaid, encoding="utf-8")
    print(f"  ✓ Mermaid → {mmd_path.relative_to(root)}", file=sys.stderr)

    png_path = assets / "graph.png"
    png_ok = render_png(mermaid, png_path)

    sys.stdout.buffer.write(("\n" + mermaid + "\n").encode("utf-8"))

    if not png_ok:
        print(
            "\n提示: PNG 渲染失败，可手动将 graph.mmd 粘贴到 https://mermaid.live 渲染",
            file=sys.stderr,
        )
        sys.exit(0)


if __name__ == "__main__":
    main()
