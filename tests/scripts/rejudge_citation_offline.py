#!/usr/bin/env python
"""fix-citation-contract-diseases 离线重判：汉森制药 002412 历史 claims 归一化后重跑。

验收（tasks.md，按实测校准）：67 条 round-2 claims（原始 41 FAIL）经归一化重判后，
FAIL = 5，全部为「stated 值在来源序列中不存在的真幻觉」（MA5=46.7 / MACD 柱=17.8、38 /
RSI=6 / BOLL 上轨=94.7——均可用序列全量搜索证伪），契约疾病归零。

归一化规则（与 delta 修 A/B 契约对齐；规则是「词表/索引语义」级 + 数据驱动行键展开，
不做逐条改值的 per-claim hack）：
1. 中文根键 → 英文 state 键（context 现已内联标注英文键，历史 claims 是中文
   标题时代的产物）；
2. technical_indicators 正索引（写于 60 期裁剪窗口语义，59=最新）→ 负索引
   （长度无关语义，59→-1，54→-6）；
3. events 根 → key_events（`[N]` 括号由 resolver 展开）；
4. 年份粒度行键（`income_statement.2025.列`）→ 按该 DataFrame 日期列前缀匹配
   展开为完整单元格值（20251231 / 2025-12-31）；
5. quarterly_trend 并行列表的季度标签（`net_profit.2026Q2`）→ 按 quarters
   标签轴换算为列表序号。

用法:
    uv run python tests/scripts/rejudge_citation_offline.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from finance_agent.citation import Claim, verify_claims  # noqa: E402

FIXTURE_PATH = ROOT / "tests" / "fixtures" / "citation_rejudge_002412.json"
CONTEXT_WINDOW = 60  # 历史运行的技术指标 context 裁剪窗口（59=最新 → -1）
FAIL_BUDGET = 5  # 实测真幻觉数（见模块 docstring）；契约疾病残量预算为 0
_DATE_COLUMNS = ("报告日", "日期")


def rebuild_state(fixture: dict) -> dict:
    """dataframes（{列: {行号: 值}}）重建 DataFrame，json 键原样并入。

    日期列归一为 date-only 字符串（'20251231' 原样；ISO Timestamp 串
    '2025-12-31T00:00:00.000' → '2025-12-31'），与运行时 datetime64 列
    astype(str) 的形式一致，且不含小数点（field_ref 点分隔语法安全）。"""
    state: dict = dict(fixture["state"].get("json") or {})
    for name, columns in (fixture["state"].get("dataframes") or {}).items():
        df = pd.DataFrame(columns).reset_index(drop=True)
        for col in _DATE_COLUMNS:
            if col in df.columns:
                df[col] = df[col].astype(str).str[:10]
        state[name] = df
    return state


_ROOT_MAP = {
    "盈利能力": "profitability_metrics",
    "偿债能力": "solvency_metrics",
    "运营效率": "efficiency_metrics",
    "现金流": "cashflow_metrics",
    "杜邦分析": "dupont_tree",
    "增长率": "growth_rates",
    "利润表": "income_statement",
    "资产负债表": "balance_sheet",
    "现金流量表": "cash_flow_statement",
    "季度趋势": "quarterly_trend",
    "健康度评分": "health_score",
    "预计算指标": "financial_indicators",
    "events": "key_events",
}


def _expand_year_rowkey(df: pd.DataFrame, year: str) -> str:
    """年份粒度行键 → 日期列（报告日/日期）中以其为前缀的最新 date-only 值。

    取 astype(str)[:10] 形式（'20251231' 原样；'2025-12-31T00:00:00.000' →
    '2025-12-31'），与 rebuild_state 的日期归一及 resolver 的等值匹配一致，
    且不含小数点（field_ref 点分隔语法安全）。"""
    date_col = next((c for c in _DATE_COLUMNS if c in df.columns), None)
    if date_col is None:
        return year
    for value in df[date_col].astype(str).str[:10]:
        if value.startswith(year):
            return value
    return year


def _expand_unit_elided_column(df: pd.DataFrame, column: str) -> str:
    """LLM 常省略列名的单位后缀（`每股净资产_调整前(元)` 写作 `每股净资产_调整前`）。

    列名去掉 `(...)` 后缀后与引用唯一同名的 → 还原为真实列名；不唯一/不存在则原样返回。
    """
    if column in df.columns:
        return column
    stripped = {str(c): re.sub(r"[(（][^)）]*[)）]$", "", str(c)).strip() for c in df.columns}
    matches = [c for c, s in stripped.items() if s == column]
    return matches[0] if len(matches) == 1 else column


def normalize_field_ref(field_ref: str, state: dict) -> str:
    """词表/索引语义归一化；不可归一化的引用原样返回（按不可路径 FAIL）。"""
    parts = field_ref.split(".")
    root = parts[0]
    if root == "technical_indicators" and len(parts) >= 4:
        # parts: technical_indicators.<组>.<序列>.<窗口内正索引>
        idx = parts[3]
        if idx.isdigit() and int(idx) < CONTEXT_WINDOW:
            parts[3] = str(int(idx) - CONTEXT_WINDOW)  # 59→-1, 54→-6
    else:
        # 词表映射兼容带括号下标的根键（events[0] → key_events[0]）
        base = re.match(r"([^\[]+)", root)
        if base and base.group(1) in _ROOT_MAP:
            parts[0] = _ROOT_MAP[base.group(1)] + root[len(base.group(1)) :]

    # DataFrame 根键的行键/列名词表展开（年份粒度行键 + 单位后缀省略）
    target = state.get(parts[0])
    if isinstance(target, pd.DataFrame) and len(parts) >= 3:
        if re.fullmatch(r"\d{4}", parts[1]):
            parts[1] = _expand_year_rowkey(target, parts[1])
        parts[-1] = _expand_unit_elided_column(target, parts[-1])
    elif parts[0] == "quarterly_trend" and len(parts) >= 3:
        # 并行列表标签 → 序号（quarters 为标签轴）
        quarters = (state.get("quarterly_trend") or {}).get("quarters") or []
        if parts[2] in quarters:
            parts[2] = str(quarters.index(parts[2]))
    return ".".join(parts)


def normalize_claim(raw: dict, state: dict) -> dict:
    out = dict(raw)
    out["field_ref"] = normalize_field_ref(str(raw.get("field_ref") or ""), state)
    if raw.get("field_ref_b"):
        out["field_ref_b"] = normalize_field_ref(str(raw["field_ref_b"]), state)
    return out


def rejudge(fixture: dict) -> tuple[list[dict], list[dict]]:
    """归一化 + 重判，返回 (results, 残量 FAIL 的归一化 claims)。"""
    state = rebuild_state(fixture)
    claims = [normalize_claim(c, state) for c in fixture["claims"]]
    results = verify_claims(
        [
            Claim.model_validate({k: v for k, v in c.items() if not k.startswith("_")})
            for c in claims
        ],
        state,
    )
    residual = [c for c, r in zip(claims, results, strict=True) if r.status == "FAIL"]
    return results, residual


def main() -> int:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    results, residual = rejudge(fixture)
    counts = {"PASS": 0, "FAIL": 0, "UNVERIFIABLE": 0}
    for r in results:
        counts[r.status] += 1

    meta = fixture.get("metadata", {})
    print(
        f"标的 {meta.get('stock_code')} round-{meta.get('claims_round')} "
        f"共 {len(results)} 条（原始 FAIL {meta.get('orig_fail')}）"
    )
    print(f"重判: {counts}")
    if residual:
        print("残量 FAIL:")
        for c in residual:
            print(f"  - {c['field_ref']} (stated={c['stated_value']})")

    if counts["FAIL"] > FAIL_BUDGET:
        print(f"验收未过: FAIL {counts['FAIL']} > 预算 {FAIL_BUDGET}")
        return 1
    print(f"验收通过: FAIL ≤ {FAIL_BUDGET}（残量应为真幻觉，契约疾病归零）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
