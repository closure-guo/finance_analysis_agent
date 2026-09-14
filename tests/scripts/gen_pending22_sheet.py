#!/usr/bin/env python
"""22 条待终裁决策单生成：137 表「待终裁」行 × r2/r4 claims 判定演化 + 证据。

背景（incident 026）：citation r2 整改轮 137 条非 PASS 中 22 条机器归因无法定论
（16 计算型未注册或空值 + 6 路径不可解析），逐条人工终裁待 owner。本脚本为终裁
备料：每条注入 r4（阶段 0–5 后校验器）同源 claim 的最新判定与 ground_truth，
附处置建议，终裁人只需对「建议」做确认/否决。

只读：仅读 tests/data/*.json 与 tests/validation/ 137 表，不调 Langfuse。

用法:
    uv run python tests/scripts/gen_pending22_sheet.py
输出:
    tests/validation/citation-22条待终裁决策单.md
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TABLE = ROOT / "tests" / "validation" / "citation-r2-nonpass-归因对照表.md"
R2 = json.loads((ROOT / "tests" / "data" / "citation_r2_claims.json").read_text("utf-8"))
R4 = json.loads((ROOT / "tests" / "data" / "citation_r4_claims.json").read_text("utf-8"))

# 已核实的证据（本脚本生成前逐条人工/代码取证）
EVIDENCE = {
    "financial_indicators.加权每股收益": "真实列名为「加权每股收益(元)」（ak.stock_financial_analysis_indicator 实测，"
    "带单位后缀）；metric_vocab「每股收益」别名表未含带后缀形态 → 列名别名缺口，校验器限制而非分析师错误",
}


def pending_rows() -> list[list[str]]:
    rows = []
    for line in TABLE.read_text(encoding="utf-8").splitlines():
        if line.startswith("|") and "待终裁" in line and "---" not in line:
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) >= 6 and cells[0].isdigit():
                rows.append(cells)
    return rows


def _norm_ref(ref: str) -> str:
    """去掉路径中的期次段，保留域与字段名。"""
    return re.sub(r"\.\d{4}(-\d{2}-\d{2})?([Qq][1-4])?(?=\.)", "", ref)


def _family(ref: str) -> str:
    """claim 家族键：域前两级 + 字段首段（MA/MACD/pmi 等），忽略期次/索引。"""
    parts = _norm_ref(ref).split(".")
    return ".".join(parts[:3]) if len(parts) >= 3 else _norm_ref(ref)


_STOCK_KEYS = ("比亚迪", "茅台", "宁德", "平安", "美的", "中芯", "招商", "招行", "中际", "拓荆")


def _trace_match(a: str, b: str) -> bool:
    """trace 名归一：r2 短名（比亚迪/分析平安）与 r4 长名（全面分析比亚迪(/贵州茅台的
    现金流）按股票词根对齐。"""
    ka = next((k for k in _STOCK_KEYS if k in a or (k == "招行" and "招商" in a)), None)
    kb = next((k for k in _STOCK_KEYS if k in b or (k == "招行" and "招商" in b)), None)
    ka = "招商" if ka == "招行" else ka
    kb = "招商" if kb == "招行" else kb
    return ka is not None and ka == kb


def family_outcomes(trace: str, ref: str) -> list[dict]:
    fam = _family(ref)
    return [
        c
        for c in R4
        if _trace_match(str(c.get("trace")), trace) and _family(str(c.get("field_ref", ""))) == fam
    ]


def find_r4(trace: str, ref: str, stated: str) -> dict | None:
    ref_n = _norm_ref(ref)
    exact = [
        c for c in R4 if c.get("trace") == trace and _norm_ref(str(c.get("field_ref", ""))) == ref_n
    ]
    same_val = [c for c in exact if str(c.get("stated_value")) == stated]
    for cand in same_val + exact:
        return cand
    return None


def find_r2(trace: str, ref: str, stated: str) -> dict | None:
    for c in R2:
        if (
            c.get("trace") == trace
            and str(c.get("field_ref", "")) == ref
            and str(c.get("stated_value")) == stated
        ):
            return c
    return None


def main() -> int:
    rows = pending_rows()
    lines = [
        "# citation 22 条待终裁决策单",
        "",
        "生成：tests/scripts/gen_pending22_sheet.py（2026-09-12）。每条含 r2 原判定、",
        "r4（阶段 0–5 后校验器）同源判定、已核实证据与处置建议。**终裁人只需逐条",
        "确认/否决「建议」列**——建议仅基于机器判定演化与代码取证，不代替人工判断。",
        "",
        "| # | trace | r2 判定 | 归因 | field_ref | stated | r4 同源判定 | r4 ground_truth | 建议 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, cells in enumerate(rows, 1):
        # 137 表列序: # | trace | 原状态 | 桶 | 归因 | 处置 | field_ref | stated | interp
        no, trace, status, bucket, attr = cells[0], cells[1], cells[2], cells[3], cells[4]
        ref, stated = cells[6], cells[7]
        r4c = find_r4(trace, ref, stated)
        r2c = find_r2(trace, ref, stated)
        if r4c:
            r4s = f"{r4c.get('status')}({r4c.get('bucket') or ''})"
        else:
            fam = family_outcomes(trace, ref)
            if fam:
                from collections import Counter

                dist = Counter(str(c.get("status")) for c in fam)
                r4s = f"同家族{len(fam)}条: " + ", ".join(f"{k}×{v}" for k, v in dist.most_common())
            else:
                r4s = "同家族 0 条"
        gt = str(r4c.get("ground_truth", ""))[:40] if r4c else ""
        ev = next((v for k, v in EVIDENCE.items() if k in ref), "")
        if r4c and r4c.get("status") == "PASS":
            sug = "校验器限制（r4 同源已修复为 PASS）→ 终裁「非幻觉」，无需处置"
        elif r4c and r4c.get("status") == "FAIL":
            sug = f"r4 同源仍 FAIL（{r4c.get('bucket')}）→ 按真错误/边界人工复核"
        elif r4c and r4c.get("status") == "UNVERIFIABLE":
            sug = "结构不可验（无注册路径）→ 终裁「非幻觉」；如需可验补注册"
        elif "加权每股收益" in ref:
            sug = "校验器限制（列名别名缺口）→ 终裁「非幻觉」；处置=词表补「加权每股收益(元)」"
        elif r4s.startswith("同家族") and "UNVERIFIABLE" not in r4s and "FAIL" not in r4s:
            sug = "r4 同家族全部 PASS（新规则吸收）→ 终裁「非幻觉」，无需处置"
        elif r4s.startswith("同家族"):
            sug = f"r4 同家族混合（{r4s}）→ 抽样人工复核该族，重点看 FAIL 项"
        else:
            sug = "r4 无同源/同家族 claim → 按原始归因人工复核"
        if ev:
            sug += f"｜证据：{ev}"
        lines.append(
            f"| {no} | {trace} | {status}{('·' + bucket) if bucket else ''} | "
            f"{attr} | {ref} | {stated} | {r4s} | {gt} | {sug} |"
        )

    # 追加：r4 收口报告「3 条加权每股收益列名待核」并入终裁清单（incident 026 §3）
    eps = [
        c for c in R4 if "加权每股收益" in str(c.get("field_ref", "")) and c.get("status") == "FAIL"
    ]
    for j, c in enumerate(eps, 1):
        lines.append(
            f"| r4-{j} | {c.get('trace')} | FAIL·path_unresolvable（r4 轮） | 列名待核 | "
            f"{c.get('field_ref')} | {c.get('stated_value')} | 本轮（r4 即最新） | | "
            "校验器限制（列名别名缺口，真实列名「加权每股收益(元)」实测）→ 终裁「非幻觉」；"
            "处置=词表补「加权每股收益(元)」别名 |"
        )
    out = ROOT / "tests" / "validation" / "citation-22条待终裁决策单.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"→ {out}（{len(rows)} 条）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
