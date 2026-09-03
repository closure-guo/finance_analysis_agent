"""最终版裁定材料生成：FM 理由按时间戳匹配注入条目 + glm 全文理由重取。

产出 reports/judge_adjudication.md（v2）：
- 6 条大分歧，每条正文内联注入对应 run 的 FM 理由（#111 修复前被丢弃的）；
- glm 独立重标重跑（全文理由，不截断；分数可能漂移——本身是证据）。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "tests" / "scripts"))

REP = Path(r"D:/WorkSpace/finance_analysis_agent/reports")

OPEN2DIM = {
    "你是投资研究报告评审专家": "report_relevance",
    "你是投资辩论质量评审专家": "debate_quality",
    "你是投资决策依据评审专家": "decision_grounding",
    "你是投资报告一致性评审专家": "consistency",
}


def _find_env() -> Path:
    for p in Path(__file__).resolve().parents:
        cand = p / ".env"
        if cand.exists():
            return cand
    return Path(".env")


def fetch_all():
    import os

    import requests
    from dotenv import load_dotenv

    load_dotenv(_find_env())
    host = "http://localhost:3000"
    auth = (os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"])
    traces = []
    for page in range(1, 10):
        r = requests.get(
            f"{host}/api/public/traces", auth=auth, params={"limit": 50, "page": page}, timeout=30
        )
        d = r.json().get("data") or []
        if not d:
            break
        traces.extend(d)
    judges, fms = [], []
    for t in traces:
        ts = str(t.get("timestamp") or "")
        name = t.get("name") or ""
        if not ts.startswith("2026-09-02") or name not in ("judge", "fund_manager"):
            continue
        full = requests.get(f"{host}/api/public/traces/{t['id']}", auth=auth, timeout=30).json()
        for o in full.get("observations") or []:
            out = o.get("output") or {}
            ans = str(out.get("answer", ""))
            inp = o.get("input") or {}
            content = next(
                (
                    str(m.get("content", ""))
                    for m in (inp.get("messages") or [])
                    if m.get("role") == "user"
                ),
                "",
            )
            if not ans and not content:
                continue
            if name == "fund_manager":
                txt = re.sub(r"^```(json)?\s*|\s*```$", "", ans.strip())
                try:
                    j = json.loads(txt, strict=False)
                    fms.append((ts, j.get("decision"), str(j.get("reasoning", ""))))
                except Exception:
                    pass
            else:
                head = content.strip()[:30]
                dim = next((v for k, v in OPEN2DIM.items() if head.startswith(k)), "?")
                score = None
                reason = ""
                m = re.search(r'"score"\s*:\s*(\d+)', ans)
                if m:
                    score = int(m.group(1))
                i = ans.find('"reason"')
                if i >= 0:
                    j2 = ans.find('"', i + 8)
                    k = ans.find('"', j2 + 1)
                    if j2 >= 0 and k > j2:
                        reason = ans[j2 + 1 : k]
                judges.append((ts, dim, content, score, reason))
            break
    return judges, fms


def main() -> None:
    judges, fms = fetch_all()
    print(f"judges={len(judges)} fms={len(fms)}")

    cross = json.loads((REP / "judge_cross_model_full.json").read_text(encoding="utf-8"))
    splits = [
        r["idx"]
        for r in cross["results"]
        if r["judge_score"] is not None
        and r["cross_score"] is not None
        and abs(r["judge_score"] - r["cross_score"]) >= 2
    ]
    print("分歧条目:", splits)

    # glm 全文重标（6 条）
    import backtest_pilot_2023 as pilot_util
    from dotenv import load_dotenv

    load_dotenv(_find_env())
    pilot_util._pin_pipeline_model()
    from finance_agent.llm.gateway import complete_text

    glm_full = {}
    for i in splits:
        ts, dim, prompt, jscore, jreason = judges[i]
        ask = (
            prompt
            + "\n\n【独立复评】请按上述同一评审标准独立打 1-5 分。只输出 JSON: "
            + '{"score": <1-5>, "reason": "<理由>"}'
        )
        try:
            answer, _ = complete_text([{"role": "user", "content": ask}], purpose="deep")
            a = str(answer)
            m = re.search(r'"score"\s*:\s*(\d+)', a)
            score = int(m.group(1)) if m else None
            ridx = a.find('"reason"')
            reason = ""
            if ridx >= 0:
                j2 = a.find('"', ridx + 8)
                k = a.find('"', j2 + 1)
                if j2 >= 0 and k > j2:
                    reason = a[j2 + 1 : k]
            glm_full[i] = {"score": score, "reason": reason}
            print(f"  [{i}] glm 重跑: {score} | {reason[:60]}")
        except Exception as e:  # noqa: BLE001
            glm_full[i] = {"score": None, "reason": f"ERROR {e}"}

    # FM 匹配 + 生成裁定表
    def match_fm(judge_ts):
        cands = [f for f in fms if f[0] < judge_ts]
        return max(cands, key=lambda f: f[0]) if cands else None

    lines = [
        "# Judge 大分歧裁定表 v2（FM 理由内联 + glm 全文理由）",
        "",
        "> 说明：①FM 理由按 run 时间戳匹配注入（#111 修复前被丢弃，现从 trace 恢复，",
        "> 标注为【#111 恢复注入】）；②glm 理由为本次全文重取（首次运行时截断了 80 字符）；",
        "> ③glm 重跑分数可能与首次不同（同输入漂移——本身就是校准证据）。",
        "",
    ]
    for i in splits:
        ts, dim, prompt, jscore, jreason = judges[i]
        fm = match_fm(ts)
        g = glm_full.get(i, {})
        # 正文注入 FM 理由
        body = prompt
        if fm and fm[1]:
            body = body.replace(
                f"【Fund Manager 最终决策】{fm[1]}",
                f"【Fund Manager 最终决策】{fm[1]}\n【#111 恢复注入·FM 理由】{fm[2]}",
            )
        lines.append(f"## 条目 {i}（{dim}）")
        lines.append(f"- **judge=({jscore})** {jreason}")
        lines.append(f"- **glm=({g.get('score')})** {g.get('reason', '')}")
        lines.append("- **你的裁定**: ____")
        lines.append("```")
        lines.append(body)
        lines.append("```")
        lines.append("")
    (REP / "judge_adjudication.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"裁定表 v2 → {REP / 'judge_adjudication.md'}")


if __name__ == "__main__":
    main()
