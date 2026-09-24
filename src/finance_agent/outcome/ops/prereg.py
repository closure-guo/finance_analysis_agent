"""预登记版本化与口径 delta 草稿(delta add-eval-ops-console Task 5,spec R6)。

本模块是「受治理编辑」的落地层,对应 spec `eval-ops-console`「预登记与口径的受治理编辑」:

- **预登记**:七个门禁字段经**与 CLI 同一套**校验(``evals.causal_ablation.preregister``
  的 ``parse_preregister`` / ``OUTCOME_REQUIRED_FIELDS``,零复制判定)后写成**新版本**文件;
  历史版本永不覆盖、永不改写(编辑 = 新增版本,「防事后改靶」由版本化本身保证)。
- **读数锁定**:``is_locked`` 判定某版本是否已产生读数——回测报告 ``**预登记**:`` 行引用,
  或 cohort 记账已有成功读数。**已知风险①(实施计划 §Task 5)** 见 ``_cohort_readings_lock``:
  真实 ``cohort_runs`` 表不记录预登记路径,该腿退化为「存在任一 success 行 ⇒ 一律锁定」。
- **口径**:``current_knobs`` 只读当前旋钮;``write_caliber_draft`` **只**在
  ``openspec/changes/`` 下生成 delta 草稿(proposal + MODIFIED 需求骨架 + §2 切点行),
  **绝不**写 ``docs/evals/metrics.md`` 与 ``evals/outcome/caliber.py``——
  「口径变更先改 §1 再动代码」的纪律由人走 delta 流程,不由界面代劳。

红线:本模块对台账与代码常量只有读权限;``write_caliber_draft`` 的全部写路径都在
``changes_dir`` 之内(见 ``tests/outcome/test_ops_prereg.py`` 的逐字节 pin 用例)。
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

from evals.causal_ablation.preregister import (
    OUTCOME_REQUIRED_FIELDS,
    parse_preregister,
)

logger = logging.getLogger("finance_agent.outcome.ops.prereg")

# 预登记目录与本实验文档过滤(与 evals.backtest.run_backtest 同源约定;ops_api 复用同值)
PREREG_DIR = Path("evals/ablation/preregister")
PREREG_NAME_CONTAINS = "outcome"
# 回测报告目录(报告 md 正文的 `**预登记**:` 行是「该版本已产生读数」的凭据)
BACKTEST_RESULTS = Path("evals/backtest/results")
# delta 草稿落点与主规范(骨架取自同名需求的所在地)
CHANGES_DIR = Path("openspec/changes")
MAIN_SPEC_PATH = Path("openspec/specs/evaluation/spec.md")
MAIN_SPEC_REQUIREMENT = "Outcome 收益指标口径与预登记"
KNOB_SOURCE = "evals/outcome/caliber.py"

# 口径数值旋钮(spec R6 点名的四项;取值只读自 evals.outcome.caliber)
KNOB_KEYS: tuple[str, ...] = (
    "PRIMARY_WINDOW_DAYS",
    "NEUTRAL_BAND",
    "LEAKAGE_PROBE_THRESHOLD",
    "MIN_SETTLED_FOR_WINRATE",
)

DRAFT_DIR_PREFIX = "ops-caliber-draft-"
# 草稿必须显式声明的生效路径(界面与草稿两处都不得省略)
DELTA_FLOW_STATEMENT = "生效须走 delta 流程"

_PREREG_LINE_RE = re.compile(r"^\*\*预登记\*\*\s*[:：]\s*(?P<value>.*)$", re.MULTILINE)
_COHORT_DB_TIMEOUT = 15.0


class InvalidPreregistration(RuntimeError):  # noqa: N818 —— 名称是实施计划约定的跨任务接口
    """预登记字段校验不过(缺字段 / 决策阈值缺换算依据 / 值含换行)——拒绝落盘。"""


class DraftExists(RuntimeError):  # noqa: N818 —— 名称是实施计划约定的跨任务接口
    """已有未处理草稿涉及同一旋钮(或同 ts 草稿目录已存在)——拒绝叠加/覆盖。"""


# ── 预登记:读取与版本化保存 ──


def _render_preregister(fields: dict[str, str], *, today: str) -> str:
    """把门禁字段渲染成门禁解析器读得懂的正文(纯函数,不落盘)。

    只输出 ``- 字段: 值`` 行(解析器全文扫描该形态),字段顺序 = 门禁声明顺序 + 额外字段。
    """
    lines = [
        f"# Outcome 收益评估预登记（{today}，运维控制台保存）",
        "",
        "> 本文件由评估运维控制台生成（`PUT /api/v1/ops/prereg`）：门禁字段经 "
        "`evals.causal_ablation.preregister.parse_preregister` 同一套校验后写入；"
        "历史版本不覆盖、不修改（编辑 = 新增版本）。口径唯一定义在 `docs/evals/metrics.md` §1.9。",
        "",
        "## 门禁字段（机器可读，`preregister.py` 解析）",
        "",
    ]
    ordered = [key for key in OUTCOME_REQUIRED_FIELDS if key in fields]
    ordered += sorted(key for key in fields if key not in OUTCOME_REQUIRED_FIELDS)
    lines += [f"- {key}: {fields[key]}" for key in ordered]
    lines.append("")
    return "\n".join(lines)


def save_prereg_version(
    fields: dict[str, str],
    *,
    dir: Path = PREREG_DIR,
    today: str | None = None,
) -> Path:
    """把门禁字段写成**新版本**预登记文件,返回新文件路径。

    校验在**落盘之前**完成,且校验对象是「渲染后的正文」——门禁读到什么就校验什么
    (与 CLI 同一套判定,不另造校验)。不合法 → ``InvalidPreregistration``,目录一个字节不动。

    文件名 ``{today}-outcome-prereg-v{n}.md``(n 递增):同日多次保存各成一版本,
    历史文件永不覆盖。``today`` 缺省取当天。
    """
    for key, value in fields.items():
        if "\n" in str(value) or "\r" in str(value):
            # 多行值会在正文里伪造出 `- 字段: 值` 行(门禁全文扫描),等于旁路校验 —— 直接拒绝
            raise InvalidPreregistration(f"字段值不得含换行: {key}")
    day = today or datetime.now().strftime("%Y-%m-%d")
    text = _render_preregister(fields, today=day)
    parsed = parse_preregister(text, required_fields=OUTCOME_REQUIRED_FIELDS)
    if not parsed.valid:
        raise InvalidPreregistration("预登记无效:" + "；".join(parsed.issues))
    directory = Path(dir)
    directory.mkdir(parents=True, exist_ok=True)
    number = 1
    while (candidate := directory / f"{day}-outcome-prereg-v{number}.md").exists():
        number += 1
    candidate.write_text(text, encoding="utf-8")
    logger.info("预登记新版本落盘: %s（%d 个门禁字段）", candidate, len(parsed.fields))
    return candidate


def list_prereg_versions(
    *,
    dir: Path = PREREG_DIR,
    name_contains: str = PREREG_NAME_CONTAINS,
    db_path: str | Path | None = None,
    backtests_dir: Path = BACKTEST_RESULTS,
) -> list[dict[str, Any]]:
    """列出本实验的预登记版本(按文件名升序),逐版本带有效性与锁定态。

    每行 ``{"path", "fields", "valid", "issues", "locked"}``——``valid``/``issues`` 与
    ``fields`` 直接来自 CLI 同一解析器;读取失败的文件按「无效 + 原因」披露,不静默跳过。
    """
    directory = Path(dir)
    if not directory.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(p for p in directory.glob("*.md") if name_contains in p.name):
        try:
            parsed = parse_preregister(
                path.read_text(encoding="utf-8"), required_fields=OUTCOME_REQUIRED_FIELDS
            )
            fields, valid, issues = dict(parsed.fields), parsed.valid, list(parsed.issues)
        except OSError as exc:
            logger.warning("预登记读取失败,按无效披露: %s", path, exc_info=True)
            fields, valid, issues = {}, False, [f"读取失败: {exc}"]
        rows.append(
            {
                "path": path.as_posix(),
                "fields": fields,
                "valid": valid,
                "issues": issues,
                "locked": is_locked(path, db_path=db_path, backtests_dir=Path(backtests_dir)),
            }
        )
    return rows


# ── 读数锁定 ──


def _backtest_references(path: Path, backtests_dir: Path) -> bool:
    """回测报告 md 的 ``**预登记**:`` 行是否引用了该版本。

    只比对**文件名**(报告渲染的是路径字符串,本地/CI 的路径分隔符与相对根不必一致;
    同名文件跨目录冲突的成本远低于漏锁)。
    """
    if not backtests_dir.exists():
        return False
    for report in sorted(backtests_dir.glob("*.md")):
        try:
            text = report.read_text(encoding="utf-8")
        except OSError:
            logger.warning("回测报告读取失败,锁定判定跳过该文件: %s", report, exc_info=True)
            continue
        if any(path.name in match.group("value") for match in _PREREG_LINE_RE.finditer(text)):
            return True
    return False


def _cohort_db_path(db_path: str | Path | None) -> Path:
    """cohort 库路径解析(与 ``outcome.cohort.model._default_db_path`` 同款约定)。

    本包不 import 该私有名(Task 1 纪律),该表达式是唯一复制点;缺省库文件不存在即视为无读数。
    """
    return Path(db_path) if db_path else Path(os.getenv("SESSIONS_DB_PATH", "data/sessions.db"))


def _cohort_readings_lock(name: str, db_path: str | Path | None) -> bool:
    """cohort 跑批腿是否已产生引用该预登记版本的读数。

    **退化实现（实施计划 §Task 5 已知风险①）**:真实 ``cohort_runs`` 表**不记录预登记
    路径**(列为 universe_version / ticker / trade_date / status / … ,无 prereg 列),故在
    schema 补列之前只能退化为「存在任一 ``success`` 行 ⇒ **所有**预登记版本一律锁定」。
    取舍:宁可过锁(界面只是提示「已有读数」,保存仍走新建版本,不阻断工作流),不可漏锁
    (漏锁 = 事后改靶的漏洞)。schema 补列后本退化自动退场(见下)。

    若未来表里出现名字含 ``prereg`` 的列,则按列匹配:值明确指向**别的**版本 → 不锁本版本;
    值提及本文件名、或值为空(来源不明)→ 锁定。库文件不存在 / 表不存在 → 无读数。
    库读取异常 → 保守判**锁定**(WARN 落日志),与「宁可过锁」一致。
    """
    db = _cohort_db_path(db_path)
    if not db.exists():
        return False
    conn = sqlite3.connect(db, check_same_thread=False, timeout=_COHORT_DB_TIMEOUT)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=15000")
        columns = [str(row["name"]) for row in conn.execute("PRAGMA table_info(cohort_runs)")]
        if not columns:
            return False  # 表不存在 ⇒ 从未跑批
        prereg_columns = [column for column in columns if "prereg" in column.lower()]
        if not prereg_columns:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM cohort_runs WHERE status = 'success'"
            ).fetchone()
            return bool(row["n"])
        column = prereg_columns[0]
        sql = f"SELECT {column} AS value FROM cohort_runs WHERE status = 'success'"  # noqa: S608
        # ^ 列名取自 PRAGMA 白名单(表结构),值全参数化:无外部输入拼接
        for row in conn.execute(sql):
            value = str(row["value"] or "").strip()
            if not value or name in value or Path(value).name == name:
                return True
        return False
    except sqlite3.DatabaseError:
        logger.warning("cohort 记账读取失败,锁定判定保守取「已锁定」: %s", db, exc_info=True)
        return True
    finally:
        conn.close()


def is_locked(
    path: Path,
    *,
    db_path: str | Path | None = None,
    backtests_dir: Path = BACKTEST_RESULTS,
) -> bool:
    """该预登记版本是否已产生读数(锁定:界面须展示「已有读数」并引导新建版本)。

    两条读数来源:回测报告 ``**预登记**:`` 行引用 + cohort 跑批成功行(退化判定,见
    ``_cohort_readings_lock`` 的取舍说明)。两条腿都无读数 → False。
    """
    return _backtest_references(Path(path), Path(backtests_dir)) or _cohort_readings_lock(
        Path(path).name, db_path
    )


# ── 口径旋钮:只读当前值 + delta 草稿生成 ──


def current_knobs() -> dict[str, float | int]:
    """当前口径旋钮值(**只读**;唯一权威定义 = ``docs/evals/metrics.md`` §1 + 代码常量)。"""
    from evals.outcome import caliber

    return {key: cast(float | int, getattr(caliber, key)) for key in KNOB_KEYS}


def _format_knob(value: float | int) -> str:
    """旋钮值渲染:整数不带小数点,浮点去尾零(0.6 不写成 0.6000000000000001)。"""
    return str(int(value)) if isinstance(value, int) else f"{value:g}"


def _read_draft_text(draft_dir: Path) -> str:
    """草稿目录内全部 md 正文(冲突判定扫全目录,不只看 proposal)。"""
    parts: list[str] = []
    for file in sorted(draft_dir.rglob("*.md")):
        try:
            parts.append(file.read_text(encoding="utf-8"))
        except OSError:
            logger.warning("草稿文件读取失败,冲突判定跳过: %s", file, exc_info=True)
    return "\n".join(parts)


def _conflicting_draft(directory: Path, knobs: set[str]) -> tuple[Path, list[str]] | None:
    """已有未处理草稿中,涉及本次任一旋钮者(``openspec/changes/`` 内的草稿;归档后不拦)。"""
    if not directory.exists():
        return None
    for draft in sorted(directory.glob(f"{DRAFT_DIR_PREFIX}*")):
        if not draft.is_dir():
            continue
        text = _read_draft_text(draft)
        hits = sorted(knob for knob in knobs if re.search(rf"\b{knob}\b", text))
        if hits:
            return draft, hits
    return None


def _extract_requirement(text: str, title: str) -> str | None:
    """从主规范正文抽出同名需求段(到下一个 ``### Requirement:`` 或二级标题为止)。"""
    lines = text.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.strip() == f"### Requirement: {title}"), None
    )
    if start is None:
        return None
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("### Requirement:") or line.startswith("## ") or line.startswith("# "):
            break
        body.append(line)
    return "\n".join(body).strip()


def _render_spec_skeleton(knobs: dict[str, float | int], *, stamp: str, spec_source: Path) -> str:
    """MODIFIED 需求骨架:标题沿用主规范同名需求,正文待评审补全(不擅自改主规范)。"""
    try:
        main_text = spec_source.read_text(encoding="utf-8")
    except OSError:
        logger.warning("主规范读取失败,骨架只出占位: %s", spec_source, exc_info=True)
        main_text = ""
    existing = _extract_requirement(main_text, MAIN_SPEC_REQUIREMENT)
    pointer = (
        f"（骨架状态：正文待补全。原始需求正文见 `{spec_source.as_posix()}` "
        f"`### Requirement: {MAIN_SPEC_REQUIREMENT}`。）"
        if existing is None
        else f"（骨架状态：正文待补全——生效时把 `{spec_source.as_posix()}` 同名需求正文整段"
        "复制到本段，仅改写旋钮取值。）"
    )
    current = current_knobs()
    change_lines = [
        f"- `{key}`: {_format_knob(current[key])} → {_format_knob(value)}"
        f"（代码位置 `{KNOB_SOURCE}`）"
        for key, value in knobs.items()
    ]
    previously = "；".join(f"{key} = {_format_knob(current[key])}" for key in knobs)
    return "\n".join(
        [
            "# Delta for evaluation",
            "",
            "## MODIFIED Requirements",
            "",
            f"### Requirement: {MAIN_SPEC_REQUIREMENT}",
            "",
            pointer,
            "",
            "本次旋钮取值变更（待评审；生效须走 delta 流程：先改 §1 口径定义，再改代码常量）：",
            "",
            *change_lines,
            "",
            f"(Previously: {previously})",
            "",
            "#### Scenario: 口径切点登记（骨架，待补全断言）",
            "",
            "- **WHEN** 本草稿评审通过并按「§1 定义 → 代码常量 → §2 切点行」落地",
            "- **THEN** `docs/evals/metrics.md` §1 与代码常量 SHALL 与新旋钮值一致",
            "- **AND** 跨切点读数 SHALL 标注不可直接比较",
            "",
            f"<!-- 生成自评估运维控制台（{DRAFT_DIR_PREFIX}{stamp}）；本目录仅为草稿，生效须走 delta 流程 -->",
            "",
        ]
    )


def _render_timeline_line(knobs: dict[str, float | int], *, stamp: str, today: str) -> str:
    """``docs/evals/metrics.md`` §2 时间线的切点行草稿(评审通过后人工追加)。"""
    current = current_knobs()
    changes = "；".join(
        f"{key} {_format_knob(current[key])} → {_format_knob(value)}"
        for key, value in knobs.items()
    )
    switchpoint = (
        f"**口径旋钮切点（{today}，delta `{DRAFT_DIR_PREFIX}{stamp}`，未跑批）**：{changes}"
        f"（代码位置 `{KNOB_SOURCE}`）。生效须先改 `docs/evals/metrics.md` §1 口径定义、再改代码常量"
        f"（本行随 delta 一并落地）；**跨此切点的读数不可直接比较**（须并列披露旧口径读数）。"
    )
    return "\n".join(
        [
            "# §2 切点行草稿（待评审，不得直接进台账）",
            "",
            "追加位置：`docs/evals/metrics.md` §2 时间线（每轮一行，收口时追加）。",
            "生效前本行留在草稿目录；`docs/evals/metrics.md` 保持原值。",
            "",
            switchpoint,
            "",
        ]
    )


def _render_proposal(knobs: dict[str, float | int], *, stamp: str) -> str:
    """proposal.md:逐旋钮现值→建议值 + 显式声明「生效须走 delta 流程」。"""
    current = current_knobs()
    table = [
        "| 旋钮 | 现值 | 建议值 | 代码位置 |",
        "|---|---|---|---|",
        *[
            f"| `{key}` | {_format_knob(current[key])} | {_format_knob(value)} | `{KNOB_SOURCE}` |"
            for key, value in knobs.items()
        ],
    ]
    return "\n".join(
        [
            f"# 口径旋钮修改草稿（`{DRAFT_DIR_PREFIX}{stamp}`）",
            "",
            "> 由评估运维控制台生成（`POST /api/v1/ops/caliber-draft`）。**这是草稿，不是生效变更**：",
            f"> **{DELTA_FLOW_STATEMENT}**——① 先改 `docs/evals/metrics.md` §1 口径定义；",
            f"> ② 再改代码常量（`{KNOB_SOURCE}`）；③ 在 §2 追加切点行（草稿见 `metrics-timeline-line.md`）。",
            "> 本草稿生成时未改动上述任何文件（逐字节不变，见 `tests/outcome/test_ops_prereg.py`）。",
            "",
            "## 旋钮变更（现值 → 建议值）",
            "",
            *table,
            "",
            f"## {DELTA_FLOW_STATEMENT}",
            "",
            "| 步骤 | 落点 | 状态 |",
            "|---|---|---|",
            "| ① 口径定义先行 | `docs/evals/metrics.md` §1 | 待评审 |",
            f"| ② 代码常量改写 | `{KNOB_SOURCE}` | 待评审 |",
            "| ③ 切点行登记 | `docs/evals/metrics.md` §2（草稿 `metrics-timeline-line.md`） | 待评审 |",
            "| ④ 评审通过后落地并跑批 | 新切点之后的读数才按新口径解释 | 待评审 |",
            "",
            "## 变更理由与影响（待补全）",
            "",
            "理由：<待补——owner 填写>",
            "",
            "预期影响：<待补——哪些读数跨切点不可直接比较>",
            "",
            "生效日期：<待补>",
            "",
        ]
    )


def _unique_stamp(directory: Path) -> str:
    """未指定 ``ts`` 时取一个未被占用的时间戳(同一秒内两次生成不得互相顶掉)。

    显式传入 ``ts`` 时不做此退让——同名目录已存在即 ``DraftExists``(由调用方负责唯一性)。
    """
    base = datetime.now()
    for offset in range(60):
        stamp = (base + timedelta(seconds=offset)).strftime("%Y%m%d-%H%M%S")
        if not (directory / f"{DRAFT_DIR_PREFIX}{stamp}").exists():
            return stamp
    raise DraftExists(
        f"无法在 {directory.as_posix()} 下分配唯一的草稿时间戳(近 60 秒目录名全被占用)"
    )


def write_caliber_draft(
    knobs: dict[str, float | int],
    *,
    changes_dir: Path = CHANGES_DIR,
    ts: str | None = None,
    spec_source: Path = MAIN_SPEC_PATH,
) -> Path:
    """旋钮修改 → ``openspec/changes/ops-caliber-draft-<ts>/`` delta 草稿,返回草稿目录。

    产出三件：``proposal.md``（逐旋钮现值→建议值 + 「生效须走 delta 流程」声明）、
    ``specs/evaluation/spec.md``（一条 MODIFIED 需求骨架）、``metrics-timeline-line.md``
    （``docs/evals/metrics.md`` §2 切点行草稿）。**不写**台账与代码常量——只读它们。

    拒绝情形：未知旋钮 / 空变更（``ValueError``）；已有未处理草稿涉及**任一**同一旋钮、
    或同一显式 ``ts`` 目录已存在（``DraftExists``，绝不叠加、绝不覆盖）。全部渲染先于建目录，
    失败不留半成品。
    """
    if not knobs:
        raise ValueError("未提供任何旋钮变更")
    unknown = sorted(set(knobs) - set(KNOB_KEYS))
    if unknown:
        raise ValueError(f"未知口径旋钮: {', '.join(unknown)}（合法旋钮: {', '.join(KNOB_KEYS)}）")
    directory = Path(changes_dir)
    conflict = _conflicting_draft(directory, set(knobs))
    if conflict is not None:
        draft_dir, hits = conflict
        raise DraftExists(
            f"已有未处理草稿 {draft_dir.as_posix()} 涉及同一旋钮: {', '.join(hits)}"
            f"（先评审/归档该草稿，或另开 delta 合并变更）"
        )
    stamp = ts if ts is not None else _unique_stamp(directory)
    draft = directory / f"{DRAFT_DIR_PREFIX}{stamp}"
    if draft.exists():
        raise DraftExists(f"草稿目录已存在: {draft.as_posix()}")
    today = datetime.now().strftime("%Y-%m-%d")
    files = {
        "proposal.md": _render_proposal(knobs, stamp=stamp),
        "specs/evaluation/spec.md": _render_spec_skeleton(
            knobs, stamp=stamp, spec_source=Path(spec_source)
        ),
        "metrics-timeline-line.md": _render_timeline_line(knobs, stamp=stamp, today=today),
    }
    (draft / "specs" / "evaluation").mkdir(parents=True, exist_ok=True)
    for relative, text in files.items():
        (draft / relative).write_text(text, encoding="utf-8")
    logger.info("口径 delta 草稿生成: %s（旋钮 %s；台账与常量未改动）", draft, ", ".join(knobs))
    return draft
