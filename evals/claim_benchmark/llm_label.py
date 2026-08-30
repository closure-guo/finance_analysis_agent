#!/usr/bin/env python
"""标注流程支持（任务 4）：LLM 初标 + 人工抽检合并 + Cohen's κ 定稿。

两个子命令：
- label   : 输入 benchmark_v1.jsonl，逐条构造标注 prompt（claim 的
  stated_value + interpretation + ground_truth + delta + 容差规则），输出
  追加 llm_label / llm_reason 两列 → 标注用 jsonl。
- finalize: 合并人工抽检标签（--human csv: entry_id,human_label），计算
  LLM 与人工的 Cohen's κ（evals.stats.cohen_kappa）；κ ≥ 0.8 → LLM 标签
  定稿为 label；< 0.8 → 分歧类以人工标签覆盖后定稿（并在报告标注该情况）。
  产出 benchmark_v1_labeled.jsonl（每条必含最终 label，空值不允许）。

标注口径（写死在 prompt 中，人工与 LLM 一致）：
  ① 模糊措辞（「约/接近」）且数值在容差内 → PASS；
  ② field_ref 路径问题不计 Agent 的错（契约已修）——judge 数值真伪而非路径；
  ③ ground_truth 缺失 → UNVERIFIABLE；
  ④ 自称 llm_inference 但有明确数据出处的 → 纠正为对应类型后再判。
容差规则：|delta| < 0.01 或 |delta| / |ground_truth| < 0.5%（相对容差）→ 数值一致。

用法:
    uv run python evals/claim_benchmark/llm_label.py label \
        --input evals/claim_benchmark/data/benchmark_v1.jsonl \
        --out evals/claim_benchmark/data/benchmark_v1_llm_labeled.jsonl

    uv run python evals/claim_benchmark/llm_label.py finalize \
        --input evals/claim_benchmark/data/benchmark_v1_llm_labeled.jsonl \
        --human evals/claim_benchmark/data/human_spotcheck.csv \
        --out evals/claim_benchmark/data/benchmark_v1_labeled.jsonl
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from evals.claim_benchmark._langfuse import _load_env  # noqa: E402
from evals.stats import cohen_kappa  # noqa: E402

PROMPT = """你是引用校验标注员。给出一条 Agent 报告中的 claim 及其校验数据，判定应有裁决。

【容差规则】（两条件满足其一即数值一致）
- 绝对容差：|delta| < 0.01
- 相对容差：|delta| / |ground_truth| < 0.5%

【标注口径】
① claim 措辞模糊（含「约/接近/左右/大约」等）且数值在容差内 → PASS；
② field_ref 路径问题（字段路径写错/中文键）不计 Agent 的错（契约已修）——
   只凭数值与 ground_truth 的关系判定，不看路径写法；
③ ground_truth 缺失（null）→ UNVERIFIABLE；
④ claim 自称 llm_inference 但 interpretation 中给出明确数据出处 →
   按实际数值类型纠正后再判。

【claim 信息】
- claim_type: {claim_type}
- source_type: {source_type}
- field_ref: {field_ref}
- stated_value: {stated_value}
- interpretation: {interpretation}

【校验数据】
- ground_truth: {ground_truth}
- delta: {delta}

只输出 JSON: {{"label": "PASS" 或 "FAIL" 或 "UNVERIFIABLE", "reason": "<一句话理由>"}}
理由须引用上述口径编号（①-④）与容差计算。"""


def _label_model() -> str:
    return os.getenv("JUDGE_MODEL", os.getenv("LLM_MODEL", "openai/deepseek-v4-flash"))


def _label_base_url() -> str:
    return os.getenv("JUDGE_BASE_URL") or os.getenv("LLM_BASE_URL", "") or ""


def _label_api_key() -> str:
    return os.getenv("JUDGE_API_KEY") or os.getenv("LLM_API_KEY", "") or ""


def _call_llm(prompt: str) -> str:
    from finance_agent.llm.gateway import complete_text

    model = _label_model()
    base_url = _label_base_url()
    if not base_url and model.startswith("deepseek/"):
        base_url = "https://api.deepseek.com/v1"
    llm_config = {"model": model, "baseUrl": base_url or "", "apiKey": _label_api_key() or ""}
    text, _meta = complete_text(
        [{"role": "user", "content": prompt}],
        purpose="judge",
        temperature=0.0,
        llm_config=llm_config,
        trace={"name": "claim_label", "metadata": {"environment": "langfuse-llm-as-a-judge"}},
    )
    return text


def _parse_json(text: str) -> dict:
    """容忍代码块/前缀噪音的 JSON 提取（与 judge 解析一致的健壮性）。"""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"未找到 JSON: {text[:120]}")
    data: dict = json.loads(m.group(0))
    return data


def _render(entry: dict) -> str:
    claim = entry["claim"]
    return PROMPT.format(
        claim_type=claim.get("claim_type"),
        source_type=claim.get("source_type"),
        field_ref=claim.get("field_ref"),
        stated_value=claim.get("stated_value"),
        interpretation=claim.get("interpretation"),
        ground_truth=entry.get("ground_truth"),
        delta=entry.get("delta"),
    )


def load_entries(path: Path) -> list[dict]:
    entries = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def write_entries(path: Path, entries: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def cmd_label(args: argparse.Namespace) -> int:
    _load_env()  # 独立 CLI 运行加载 .env（LLM 网关凭据；测试 monkeypatch _call_llm 不受影响）
    entries = load_entries(Path(args.input))
    print(f"待标注 {len(entries)} 条")
    for i, e in enumerate(entries):
        prompt = _render(e)
        for _attempt in range(2):
            try:
                data = _parse_json(_call_llm(prompt))
                label = str(data.get("label", "")).strip().upper()
                if label not in {"PASS", "FAIL", "UNVERIFIABLE"}:
                    raise ValueError(f"非法 label: {label}")
                e["llm_label"] = label
                e["llm_reason"] = str(data.get("reason", ""))
                break
            except Exception as exc:  # noqa: BLE001 - 重试一次后兜底 UNVERIFIABLE+解析失败
                last_err = exc
        else:
            e["llm_label"] = "UNVERIFIABLE"
            e["llm_reason"] = f"llm_parse_failed: {last_err}"
        if (i + 1) % 25 == 0 or i == len(entries) - 1:
            print(f"  进度 {i + 1}/{len(entries)}")
    write_entries(Path(args.out), entries)
    from collections import Counter

    print("LLM 标签分布:", dict(Counter(e["llm_label"] for e in entries)))
    print(f"已写 {Path(args.out)}")
    return 0


def _load_human_labels(path: Path) -> dict[str, str]:
    labels: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            eid = (row.get("entry_id") or "").strip()
            lab = (row.get("human_label") or "").strip().upper()
            if eid and lab:
                labels[eid] = lab
    return labels


def cmd_finalize(args: argparse.Namespace) -> int:
    entries = load_entries(Path(args.input))
    human = _load_human_labels(Path(args.human))
    paired: list[tuple[str, str, str]] = []
    for e in entries:
        if e["entry_id"] in human and e.get("llm_label"):
            paired.append((e["entry_id"], str(e["llm_label"]), human[e["entry_id"]]))
    kappa: float | None = None
    verdict = "no_human_check"
    if paired:
        llm_labels = [p[1] for p in paired]
        human_labels = [p[2] for p in paired]
        kappa = cohen_kappa(llm_labels, human_labels)
        verdict = "llm_final" if (kappa or 0.0) >= 0.8 else "human_overrides_disagreements"

    for e in entries:
        eid = e["entry_id"]
        if eid in human:
            hu = human[eid]
            ll = e.get("llm_label")
            if (kappa or 0.0) >= 0.8 or ll == hu:
                e["label"] = ll
            else:
                e["label"] = hu  # 分歧以人工为准
            e["human_label"] = hu
        else:
            # 未抽检条目：LLM 标签定稿（κ 达标时证据充分；未达标时待人工补抽）
            e["label"] = e.get("llm_label")
        if not e.get("label"):
            raise SystemExit(f"{eid}: 最终 label 为空（LLM 解析失败且未人工抽检）")

    write_entries(Path(args.out), entries)
    from collections import Counter

    print(f"人工抽检 {len(paired)} 条；Cohen's κ = {kappa if kappa is not None else '（未抽检）'}")
    print(f"定稿方式: {verdict}")
    print("最终 label 分布:", dict(Counter(e["label"] for e in entries)))
    print(f"已写 {Path(args.out)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="基准集标注（LLM 初标 + 人工合并 + κ）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("label", help="LLM 初标")
    p1.add_argument("--input", required=True)
    p1.add_argument("--out", required=True)
    p1.set_defaults(func=cmd_label)
    p2 = sub.add_parser("finalize", help="合并人工抽检并定稿")
    p2.add_argument("--input", required=True)
    p2.add_argument("--human", required=True, help="人工标签 CSV（entry_id,human_label）")
    p2.add_argument("--out", required=True)
    p2.set_defaults(func=cmd_finalize)
    args = ap.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
