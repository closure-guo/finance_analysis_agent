"""r2 真实语料常驻回归集（infer-period-for-unindexed-series §2）。

数据源：`tests/data/citation_r2_claims.json`（565 条真实 claim，r2 轮次 incident 026
归因材料；137 条非 PASS 的归因见 `tests/validation/citation-r2-nonpass-归因对照表.md`，
22 条待终裁见 `citation-22条待终裁决策单.md`——结论：137 条全部「非幻觉」，误判源头
在校验器的解析/术语/期次层）。

重放方式：按**生产者真实形状**构造 state（而非照 claim 的路径拼）——这样归一化缺口
（日期显示格式、季度标签与顺序、列名单位后缀、词表别名、期次缺省）才会被真正触发：
- `quarterly_trend`：`compute.py::_calc_quarterly_trend` 的 quarters + 平行列表，
  季度**降序**（实测 `cache.db` 600519:quarterly_income 季度列 = [2026Q2, 2026Q1, …]）；
- `technical_indicators`：`metrics/technical.py::calc_technical` 的 {指标: {参数: 序列}}；
- `macro_indicators`：fetch 守卫结构 records 列表（`月份` + 指标列）；
- 报表域：DataFrame，行键按生产者存储形态（三大报表 `报告日`=`20251231` 字符串、
  indicators `日期`；均为**降序**，最新在前）；indicators 列名带单位后缀；
- `news_list` / `key_events`：标题文本（文本 claim 的回声源）；
- 其余指标根键：按字段路径嵌套 dict（dupont_tree.L1.2025.权益乘数 / health_score.total）。

不变量：
1. 137 条非 PASS 中，除 `_EXPECTED_FAIL_ALLOWLIST`（逐条注明理由：真错或契约强制）外
   SHALL NOT 判 FAIL——校验器限制不得记成分析师错误（incident 026）；
2. 428 条 PASS SHALL 维持 PASS（解析/术语改动不得把正确引用打成 FAIL）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from finance_agent.citation import Claim, verify_claims

_CORPUS = json.loads(
    (Path(__file__).parent / "data" / "citation_r2_claims.json").read_text(encoding="utf-8")
)

# 期望 FAIL 白名单：(trace, field_ref) → 理由。仅两类——真错、或契约强制（非误报）。
_EXPECTED_FAIL_ALLOWLIST: dict[tuple[str, str], str] = {
    # 契约强制：comparative 单端申报（缺 field_ref_b/stated_value_b）按
    # citation-verification「comparative 基期值双端申报与校验」SHALL 判 FAIL；
    # 三分析师 prompt 已强制双端申报纪律（fundamental/technical 第 9 条、macro 第 7 条），
    # 语料是契约生效前的历史快照——FAIL 是契约执行结果，不是校验器误报。
    ("中芯", "macro_indicators.m2.0.货币和准货币(M2)-同比增长"): "comparative 单端（契约强制）",
    ("分析平安", "macro_indicators.m2.0.货币和准货币(M2)-同比增长"): "comparative 单端（契约强制）",
    ("宁德", "profitability_metrics.净利率.2025"): "comparative 单端（契约强制）",
    ("宁德", "solvency_metrics.资产负债率.2025"): "comparative 单端（契约强制）",
    ("宁德", "efficiency_metrics.存货周转率.2025"): "comparative 单端（契约强制）",
    ("平安", "macro_indicators.pmi.0.制造业-指数"): "comparative 单端（契约强制）",
    ("平安", "macro_indicators.m2.0.货币和准货币(M2)-同比增长"): "comparative 单端（契约强制）",
    ("比亚迪", "macro_indicators.pmi.1.制造业-指数"): "comparative 单端（契约强制）",
    ("茅台", "macro_indicators.cpi.0.全国-同比增长"): "comparative 单端（契约强制）",
}


def _truth(claim: dict) -> float | None:
    """重放用候选值：ground_truth 优先（校验器当时真实解析到的读数），缺省用申报值。

    137 条非 PASS 的终裁结论为「全部非幻觉」——申报值即真值；但同地址若已有
    ground_truth（权威读数）则以权威为准（防 claim 间互相覆盖）。文本 claim
    （实体/事件/枚举）无数值真值 → None。
    """
    gt = claim.get("ground_truth")
    if isinstance(gt, int | float):
        return float(gt)
    try:
        return float(claim["stated_value"])
    except (TypeError, ValueError):
        return None


_QUARTER_RE = re.compile(r"((?:19|20)\d{2})\s*[Qq]([1-4])")
_FRAME_ROOTS = ("income_statement", "balance_sheet", "cash_flow_statement", "financial_indicators")
_FRAME_KEY_COL = {"financial_indicators": "日期"}
# akshare 指标表真实列名（astock 实测带单位后缀）——claim 常省略后缀，构造时按真实列名落值
_REAL_INDICATOR_COLUMNS = {
    "加权每股收益": "加权每股收益(元)",
    "摊薄每股收益": "摊薄每股收益(元)",
    "加权净资产收益率": "加权净资产收益率(%)",
    "净资产收益率": "净资产收益率(%)",
    "股息发放率": "股息发放率(%)",
    "存货周转率": "存货周转率(次)",
}


def _series_key(seg: str) -> str:
    """序列名去 `[N]` 括号（field_ref 两种索引写法：`yoy.0` 与 `yoy[0]`）。"""
    return re.sub(r"\[.*\]$", "", seg)


def _prev_quarter(label: str) -> str:
    year, quarter = int(label[:4]), int(label[-1])
    return f"{year - 1}Q4" if quarter == 1 else f"{year}Q{quarter - 1}"


def _quarter_axis(claims: list[dict]) -> list[str]:
    """该 trace 的季度轴：**连续**覆盖（降序，最新在前）+ 补足被引用的最大索引。

    生产者顺序由实测钉死：`cache.db` 600519:quarterly_income 季度列降序，
    与 `_calc_quarterly_trend` 逐行迭代一致；r2 语料 `quarterly_trend.yoy[0]` +
    正文「2026Q2」互证（索引 0 即最新季）。中间季可能无 claim 提及（如 2026Q1），
    但生产者序列必然连续 → 补齐，否则索引引用会错位。
    """
    labels: set[str] = set()
    for c in claims:
        for text in (
            c.get("field_ref") or "",
            c.get("interpretation") or "",
            c.get("period") or "",
        ):
            labels.update(f"{m.group(1)}Q{m.group(2)}" for m in _QUARTER_RE.finditer(text))
    if not labels:
        return []
    newest = max(labels, key=lambda s: (int(s[:4]), int(s[-1])))
    oldest = min(labels, key=lambda s: (int(s[:4]), int(s[-1])))
    axis = [newest]
    while axis[-1] != oldest:
        axis.append(_prev_quarter(axis[-1]))
    needed = 0
    for c in claims:
        for m in re.finditer(r"\[(-?\d+)\]", c.get("field_ref") or ""):
            needed = max(needed, int(m.group(1)) + 1)
    while len(axis) < needed:
        axis.append(_prev_quarter(axis[-1]))
    return axis


def _series_pos(claim: dict, quarters: list[str]) -> int | None:
    """序列元素位置：路径显式索引 / `[N]` 括号 / 季度标签 → 正文或 period 季度标签。"""
    parts = (claim.get("field_ref") or "").split(".")
    if parts and re.fullmatch(r"-?\d+", parts[-1]):
        return int(parts[-1])
    bracket = re.search(r"\[(-?\d+)\]$", parts[-1]) if parts else None
    if bracket:
        return int(bracket.group(1))
    if parts and parts[-1].upper() in quarters:
        return quarters.index(parts[-1].upper())
    for text in (claim.get("period") or "", claim.get("interpretation") or ""):
        hits = {f"{m.group(1)}Q{m.group(2)}" for m in _QUARTER_RE.finditer(text)}
        if len(hits) == 1:
            label = hits.pop()
            if label in quarters:
                return quarters.index(label)
    return None


def _series_label_pos(claim: dict, quarters: list[str]) -> int | None:
    """仅按季度标签定位（不带索引回落），供「地址是否已落值」判定用。"""
    for text in (
        claim.get("field_ref") or "",
        claim.get("period") or "",
        claim.get("interpretation") or "",
    ):
        hits = {f"{m.group(1)}Q{m.group(2)}" for m in _QUARTER_RE.finditer(text)}
        if len(hits) == 1:
            label = hits.pop()
            if label in quarters:
                return quarters.index(label)
    return None


def _nest_set(tree: dict, parts: list[str], value: object) -> None:
    """按路径逐层建 dict 并落值（任意深度；指标 dict / dupont / health_score）。"""
    cur = tree
    for seg in parts[:-1]:
        cur = cur.setdefault(seg, {})
    cur[parts[-1]] = value


def _placed(containers: dict[str, Any], claim: dict, quarters: list[str]) -> bool:
    """claim 的地址当前是否已落值（非权威趟避免覆盖权威读数）。"""
    parts = (claim.get("field_ref") or "").split(".")
    root = parts[0] if parts else ""
    if root == "quarterly_trend" and len(parts) >= 2:
        seq = containers["trend"].get(_series_key(parts[1]))
        pos = _series_label_pos(claim, quarters)
        return bool(seq) and pos is not None and seq[pos] is not None
    if root == "technical_indicators" and len(parts) >= 4 and re.fullmatch(r"-?\d+", parts[3]):
        seq = containers["tech"].get(parts[1], {}).get(parts[2])
        return bool(seq) and seq[int(parts[3])] is not None
    if root == "macro_indicators" and len(parts) >= 4 and re.fullmatch(r"-?\d+", parts[2]):
        rec = containers["macro"].get(parts[1], {}).get(int(parts[2]), {})
        return rec.get(".".join(parts[3:])) is not None
    if root in _FRAME_ROOTS and len(parts) >= 3:
        col = _REAL_INDICATOR_COLUMNS.get(parts[-1], parts[-1])
        row = containers["frames"].get(root, {}).get(parts[-2].replace("-", ""), {})
        return row.get(col) is not None
    cur: Any = containers["metrics"]
    for seg in parts:
        if not isinstance(cur, dict) or seg not in cur:
            return False
        cur = cur[seg]
    return cur is not None


def _build_state(claims: list[dict]) -> dict:
    """按生产者真实形状构造该 trace 的 state（落值两趟，权威读数优先）。"""
    quarters = _quarter_axis(claims)
    news: dict[int, dict] = {}
    events: dict[int, dict] = {}
    trend: dict[str, Any] = {"quarters": quarters, "warnings": []}
    for series in ("net_profit", "qoq", "yoy"):
        trend[series] = [None] * len(quarters)
    tech: dict[str, dict[str, list]] = {}
    macro: dict[str, dict[int, dict]] = {}
    frames: dict[str, dict[str, dict]] = {}
    metrics: dict[str, Any] = {}
    containers = {
        "trend": trend,
        "tech": tech,
        "macro": macro,
        "frames": frames,
        "metrics": metrics,
    }

    def place(c: dict, authoritative: bool) -> None:
        parts = (c.get("field_ref") or "").split(".")
        root = parts[0] if parts else ""
        stated, truth = str(c.get("stated_value")), _truth(c)
        if len(parts) < 2:
            return
        if root == "news_list":
            idx = int(parts[1]) if parts[1].isdigit() else len(news)
            news.setdefault(idx, {"title": stated})
            return
        if root == "key_events":
            idx = int(parts[1]) if parts[1].isdigit() else len(events)
            events.setdefault(idx, {"title": stated})
            return
        if not authoritative and _placed(containers, c, quarters):
            return
        if root == "quarterly_trend" and _series_key(parts[1]) in trend:
            pos = _series_pos(c, quarters)
            if truth is not None and pos is not None and 0 <= pos < len(quarters):
                trend[_series_key(parts[1])][pos] = truth
            return
        if root == "technical_indicators" and len(parts) >= 4 and re.fullmatch(r"-?\d+", parts[3]):
            if truth is None:
                return
            seq = tech.setdefault(parts[1], {}).setdefault(parts[2], [0.0] * 40)
            seq[int(parts[3])] = truth
            return
        if root == "macro_indicators" and len(parts) >= 4 and re.fullmatch(r"-?\d+", parts[2]):
            if truth is None:
                return
            macro.setdefault(parts[1], {}).setdefault(int(parts[2]), {})[".".join(parts[3:])] = (
                truth
            )
            return
        if root in _FRAME_ROOTS:
            if len(parts) >= 3 and truth is not None:
                col = _REAL_INDICATOR_COLUMNS.get(parts[-1], parts[-1])
                frames.setdefault(root, {}).setdefault(parts[-2].replace("-", ""), {})[col] = truth
            return
        _nest_set(metrics, parts, truth if truth is not None else stated)

    for c in claims:  # 趟 1：权威读数（r2 真实解析到的 ground_truth）
        if c.get("ground_truth") is not None:
            place(c, authoritative=True)
    for c in claims:  # 趟 2：其余按申报值补，不覆盖
        if c.get("ground_truth") is None:
            place(c, authoritative=False)

    state: dict = {}
    if news:
        state["news_list"] = [news.get(i, {"title": ""}) for i in range(max(news) + 1)]
    if events:
        state["key_events"] = [events.get(i, {"title": ""}) for i in range(max(events) + 1)]
    if quarters:
        state["quarterly_trend"] = trend
    if tech:
        state["technical_indicators"] = tech
    if macro:
        state["macro_indicators"] = {
            k: [recs.get(i, {}) for i in range(max(recs) + 1)] for k, recs in macro.items()
        }
    for root, rows in frames.items():
        key_col = _FRAME_KEY_COL.get(root, "报告日")
        # 生产者降序（最新在前）：实测 cache.db 三大报表 20251231 → 20241231 → 20231231
        state[root] = pd.DataFrame(
            [{key_col: key, **cols} for key, cols in sorted(rows.items(), reverse=True)]
        )
    for root, tree in metrics.items():
        state.setdefault(root, {})
        for key, value in tree.items():
            if isinstance(value, dict) and isinstance(state[root].get(key), dict):
                state[root][key] = {**state[root][key], **value}
            else:
                state[root][key] = value
    return state


def _by_trace() -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for c in _CORPUS:
        grouped.setdefault(c["trace"], []).append(c)
    return grouped


def _replay(claims: list[dict], trace: str) -> list[tuple[dict, Any]]:
    """重放：state 按该 trace **全量** claim 构造（轴/结构完整），只校验传入子集。"""
    state = _build_state(_by_trace()[trace])
    out = []
    for c in claims:
        payload = {k: v for k, v in c.items() if k not in ("trace", "status", "bucket")}
        out.append((c, verify_claims([Claim.model_validate(payload)], state)[0]))
    return out


_TRACES = sorted(_by_trace())


@pytest.mark.parametrize("trace", _TRACES)
def test_r2_pass_claims_stay_pass(trace: str):
    """428 条 PASS 不回归：解析/术语/期次改动不得把正确引用打成 FAIL。"""
    claims = [c for c in _by_trace()[trace] if c["status"] == "PASS"]
    regressions = [
        (c["field_ref"], r.status, r.bucket, r.ground_truth)
        for c, r in _replay(claims, trace)
        if r.status != "PASS"
    ]
    assert not regressions, f"{trace} PASS 回归 {len(regressions)} 条：{regressions[:6]}"


@pytest.mark.parametrize("trace", _TRACES)
def test_r2_nonpass_claims_have_no_unjustified_fail(trace: str):
    """137 条非 PASS（终裁全为非幻觉）：除白名单外不得判 FAIL。"""
    claims = [c for c in _by_trace()[trace] if c["status"] != "PASS"]
    if not claims:
        pytest.skip("该 trace 无非 PASS claim")
    bad = [
        (c["field_ref"], r.status, r.bucket, c["stated_value"])
        for c, r in _replay(claims, trace)
        if r.status == "FAIL" and (trace, c["field_ref"]) not in _EXPECTED_FAIL_ALLOWLIST
    ]
    assert not bad, f"{trace} 非 PASS 仍误 FAIL {len(bad)} 条：{bad[:8]}"


def test_corpus_covers_all_nonpass_classes():
    """护栏：语料本身不得被裁剪（565 条 / 137 非 PASS / 9 traces）。"""
    assert len(_CORPUS) == 565
    assert sum(1 for c in _CORPUS if c["status"] != "PASS") == 137
    assert len(_TRACES) == 9
