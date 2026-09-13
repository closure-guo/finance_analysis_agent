"""两个 delta 的端到端真实验证驱动（report-render-operational-params 4.2 /
deterministic-derived-metrics 4.3）。

跑真实 5 层管线，产出验证记录到 tests/validation/：
- 派生指标：validate 节点代码计算值 vs 风险辩论各方 reasoning 中引用的赔率/止损距离
  （辩论方是否同源引用，而非各自心算）
- 报告：决策节渲染仓位/入场/止损/目标价与派生指标行，数值与决策 JSON 同源

用法：uv run python tests/scripts/verify_deltas_e2e.py 600036 招商银行 600519 贵州茅台
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from finance_agent.graph import build_5layer_graph  # noqa: E402


def run_one(stock_code: str, stock_name: str) -> dict:
    from finance_agent.langfuse_tracing import get_callback_handler

    graph = build_5layer_graph()
    initial_state = {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "analysis_type": "comprehensive",
        "peer_codes": None,
        "enable_web_search": False,
        "api_key": None,
        "focus": f"全面分析{stock_name}（{stock_code}），当前能不能买？",
        "llm_config": None,
    }
    handler = get_callback_handler()
    config = {"callbacks": [handler]} if handler else None
    state = graph.invoke(initial_state, config=config)
    return state


def verify(state: dict, stock_code: str) -> dict:
    """提取验证事实：派生指标、辩论引用、报告决策节。"""
    dm = state.get("derived_metrics") or {}
    decision = state.get("final_trade_decision")
    if hasattr(decision, "model_dump"):
        decision = decision.model_dump()
    debates = []
    for msg in state.get("risk_debate_history") or []:
        role = msg.get("role", "?") if isinstance(msg, dict) else getattr(msg, "role", "?")
        content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
        debates.append({"role": role, "mentions_ratio": None, "mentions_stop_pct": None, "excerpt": content[:200]})

    ratio = dm.get("risk_reward_ratio")
    stop_pct = dm.get("stop_distance_pct")
    if ratio is not None:
        ratio_strs = [f"{ratio:.2f}:1", f"{ratio:.1f}:1", f"{ratio:.2f}", f"{ratio:.1f}"]
        stop_strs = [f"{stop_pct:.1%}", f"{stop_pct * 100:.1f}%"]
        for d in debates:
            d["mentions_ratio"] = any(s in d["excerpt"] or s in _full_content(state, d["role"]) for s in ratio_strs)
            d["mentions_stop_pct"] = any(s in d["excerpt"] or s in _full_content(state, d["role"]) for s in stop_strs)

    report = state.get("final_report") or ""
    decision_section = ""
    if report:
        lines, on = [], False
        for ln in report.split("\n"):
            if "交易决策" in ln:
                on = True
                continue
            if on and ln.startswith("#"):
                break
            if on:
                lines.append(ln)
        decision_section = "\n".join(lines)

    return {
        "stock_code": stock_code,
        "action": (decision or {}).get("action"),
        "derived_metrics": dm,
        "decision_params": {
            k: (decision or {}).get(k) for k in ("position_size", "entry_price", "stop_loss", "target_price")
        },
        "debates": debates,
        "decision_section": decision_section,
        "price_check": state.get("price_check"),
    }


def _full_content(state: dict, role: str) -> str:
    for msg in state.get("risk_debate_history") or []:
        r = msg.get("role", "?") if isinstance(msg, dict) else getattr(msg, "role", "?")
        if r == role:
            return msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
    return ""


def main() -> None:
    args = sys.argv[1:]
    records = []
    for i in range(0, len(args), 2):
        code, name = args[i], args[i + 1]
        print(f"=== 运行 {name}({code}) ===", flush=True)
        state = run_one(code, name)
        rec = verify(state, code)
        records.append(rec)
        print(f"action={rec['action']} derived={rec['derived_metrics']}", flush=True)

    out = Path("tests/validation/delta-e2e-验证记录.md")
    lines = [f"# 两个 delta 端到端验证记录（{datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}）\n"]
    for rec in records:
        lines.append(f"## {rec['stock_code']}——action={rec['action']}\n")
        lines.append(f"- price_check: `{rec['price_check']}`")
        lines.append(f"- 决策参数: `{rec['decision_params']}`")
        lines.append(f"- 派生指标（代码计算）: `{rec['derived_metrics']}`\n")
        lines.append("**风险辩论引用情况**（mentions = reasoning 中出现代码计算的赔率/止损距离数值）:\n")
        for d in rec["debates"]:
            lines.append(f"- {d['role']}: mentions_ratio={d['mentions_ratio']} mentions_stop_pct={d['mentions_stop_pct']}")
        lines.append("\n**报告决策节**:\n\n```\n" + rec["decision_section"] + "\n```\n")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"验证记录 → {out}", flush=True)


if __name__ == "__main__":
    main()
