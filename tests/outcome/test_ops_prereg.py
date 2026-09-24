"""Task 5(delta add-eval-ops-console):预登记版本化 + 读数锁定 + 口径 delta 草稿。

覆盖面:

1. ``save_prereg_version``——校验不过**不落盘**;写新版本文件**不覆盖历史**;
   写出的文件能过 CLI 同一套门禁(``preregister.assert_preregistered``),
   保证「界面保存的版本 = 门禁读得到的版本」而非两套校验;
2. ``is_locked``——回测报告 ``**预登记**:`` 行引用即锁定;cohort 侧退化路径
   (``cohort_runs`` 无预登记路径列 → 存在任一 ``success`` 行即锁定,见函数 docstring
   与实施计划 §Task 5 已知风险①);未来 schema 真加了预登记列时按列匹配(不误锁);
3. ``write_caliber_draft``——只生成 delta 草稿(``proposal.md`` / MODIFIED 需求骨架 /
   §2 切点行),**绝不**写 ``docs/evals/metrics.md`` 与 ``evals/outcome/caliber.py``
   (逐字节 pin 真实仓库文件);同一旋钮已有未处理草稿 → ``DraftExists``。

全部用例零网络零 LLM、只写 tmp_path(台账/常量两份真实文件仅读取后比对字节)。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from evals.causal_ablation.preregister import (
    OUTCOME_REQUIRED_FIELDS,
    assert_preregistered,
)

from finance_agent.outcome.cohort.model import init_cohort_runs, insert_cohort_run
from finance_agent.outcome.ops.prereg import (
    KNOB_KEYS,
    DraftExists,
    InvalidPreregistration,
    current_knobs,
    is_locked,
    list_prereg_versions,
    save_prereg_version,
    write_caliber_draft,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
# 红线两文件:口径草稿生成前后必须逐字节不变(相对仓库根解析,不怕用例改 cwd)
LEDGER = REPO_ROOT / "docs" / "evals" / "metrics.md"
CALIBER_MODULE = REPO_ROOT / "evals" / "outcome" / "caliber.py"

# 七个门禁字段齐备 + 决策阈值带换算依据(与 tests/test_ops_api.py 的正文同源口径)
VALID_FIELDS: dict[str, str] = {
    "主指标": "逐决策 T+20 相对沪深300 超额收益均值与胜率",
    "MDE": "n=30 → 5.1pp（换算依据见 §4）",
    "决策阈值": "均值超额 95% CI 下限 > 0；依据：标的簇 bootstrap CI",
    "样本量依据": "forward ≥10 / ≥30 / ≥100（MDE 反算）",
    "停止规则": "健康检查不过作废；探针 >0.60 降级",
    "成本分型": "forward 每标的 1 次 deep；回测 回放 ×3 + 探针",
    "泄漏控制": "干净窗口 + 探针披露（阈值 0.60）",
}


# ── 1. save_prereg_version:校验前置、新版本、不覆盖历史 ──


def test_save_rejects_invalid_fields_without_touching_disk(tmp_path):
    """缺字段(MDE 等)→ InvalidPreregistration;目录**一个文件都不许多**。"""
    before = sorted(p.name for p in tmp_path.iterdir())
    with pytest.raises(InvalidPreregistration, match="MDE"):
        save_prereg_version({"主指标": "x"}, dir=tmp_path)
    assert list(tmp_path.glob("*.md")) == []
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_save_rejects_bare_threshold_without_rationale(tmp_path):
    """决策阈值为裸数字(缺换算依据)同样拒绝——与 CLI 门禁同一套判定。"""
    fields = {**VALID_FIELDS, "决策阈值": "0.5"}
    with pytest.raises(InvalidPreregistration, match="换算依据"):
        save_prereg_version(fields, dir=tmp_path)
    assert list(tmp_path.glob("*.md")) == []


def test_save_writes_new_version_without_touching_history(tmp_path):
    old = tmp_path / "2026-01-01-outcome-a.md"
    old.write_text("历史版本", encoding="utf-8")
    new = save_prereg_version(VALID_FIELDS, dir=tmp_path, today="2026-09-24")
    assert new.parent == tmp_path
    assert new.name.startswith("2026-09-24-")
    assert "outcome" in new.name  # 门禁的 name_contains 过滤必须命中
    assert old.read_text(encoding="utf-8") == "历史版本"
    assert new.read_text(encoding="utf-8") != "历史版本"


def test_save_twice_same_day_never_overwrites(tmp_path):
    """同日两次保存各成一个版本文件,先写的内容不得被后写覆盖。"""
    first = save_prereg_version(VALID_FIELDS, dir=tmp_path, today="2026-09-24")
    body = first.read_text(encoding="utf-8")
    second = save_prereg_version(
        {**VALID_FIELDS, "MDE": "n=100 → 2.8pp（换算依据见 §4）"},
        dir=tmp_path,
        today="2026-09-24",
    )
    assert second != first
    assert first.read_text(encoding="utf-8") == body
    assert len(list(tmp_path.glob("2026-09-24-*.md"))) == 2


def test_saved_version_passes_cli_gate(tmp_path):
    """写出的文件必须能被既有门禁函数直接读为「有效」——守卫「界面保存另一套校验」的漂移。"""
    path = save_prereg_version(VALID_FIELDS, dir=tmp_path, today="2026-09-24")
    found = assert_preregistered(
        tmp_path, name_contains="outcome", required_fields=OUTCOME_REQUIRED_FIELDS
    )
    assert found.path == path
    assert found.valid is True
    assert {key: found.fields[key] for key in OUTCOME_REQUIRED_FIELDS} == VALID_FIELDS


# ── 2. list_prereg_versions ──


def test_list_reports_path_fields_valid_issues_locked(tmp_path):
    good = save_prereg_version(VALID_FIELDS, dir=tmp_path, today="2026-09-24")
    bad = tmp_path / "2026-09-25-outcome-bad.md"
    bad.write_text("- 主指标: x\n", encoding="utf-8")
    (tmp_path / "2026-09-25-not-ours.md").write_text("- 主指标: x\n", encoding="utf-8")
    backtests = tmp_path / "bt"
    backtests.mkdir()
    (backtests / "formal-1.md").write_text(
        f"**预登记**: {good.as_posix()}（valid）\n**status**: active\n", encoding="utf-8"
    )

    rows = list_prereg_versions(dir=tmp_path, backtests_dir=backtests)

    # 只列本实验文档(name_contains="outcome"),按文件名升序
    assert [Path(row["path"]).name for row in rows] == [good.name, bad.name]
    good_row, bad_row = rows
    assert set(good_row) == {"path", "fields", "valid", "issues", "locked"}
    assert good_row["valid"] is True
    assert good_row["issues"] == []
    assert good_row["fields"]["MDE"] == VALID_FIELDS["MDE"]
    assert good_row["locked"] is True
    assert bad_row["valid"] is False
    assert any("MDE" in issue for issue in bad_row["issues"])
    assert bad_row["locked"] is False


def test_list_on_missing_dir_is_empty(tmp_path):
    assert list_prereg_versions(dir=tmp_path / "nope", backtests_dir=tmp_path / "bt") == []


# ── 3. is_locked:回测报告引用 + cohort 退化 ──


def test_lock_detects_reading_reference(tmp_path):
    path = tmp_path / "2026-09-23-outcome-x.md"
    path.write_text("- 主指标: x", encoding="utf-8")
    backtests = tmp_path / "bt"
    backtests.mkdir()
    (backtests / "other.md").write_text(
        "**预登记**: /elsewhere/2026-01-01-outcome-zzz.md（valid）\n", encoding="utf-8"
    )
    assert is_locked(path, backtests_dir=backtests) is False

    (backtests / "formal-1.md").write_text(
        f"**预登记**: {path.as_posix()}（valid）\n**status**: active\n", encoding="utf-8"
    )
    assert is_locked(path, backtests_dir=backtests) is True


def test_lock_without_readings_is_false_and_creates_nothing(tmp_path):
    """无任何读数(回测目录不存在 + cohort 库不存在)→ False,且读取不得建库建目录。"""
    path = tmp_path / "2026-09-23-outcome-x.md"
    path.write_text("- 主指标: x", encoding="utf-8")
    db = tmp_path / "no-such.db"
    assert is_locked(path, db_path=db, backtests_dir=tmp_path / "bt") is False
    assert not db.exists()


def test_lock_degrades_to_any_success_cohort_run(tmp_path):
    """真实 schema(无预登记路径列)→ 退化:存在任一 success 行即锁定;仅失败行不锁。"""
    path = tmp_path / "2026-09-23-outcome-x.md"
    path.write_text("- 主指标: x", encoding="utf-8")
    db = tmp_path / "sessions.db"
    backtests = tmp_path / "bt"  # 不存在 = 无回测报告

    assert is_locked(path, db_path=db, backtests_dir=backtests) is False  # 无库

    init_cohort_runs(db)
    insert_cohort_run(
        {
            "universe_version": "universe-v1",
            "ticker": "600519",
            "trade_date": "2026-09-23",
            "status": "failure",
            "trigger_time": "2026-09-23T18:00:00",
        },
        db_path=db,
    )
    assert is_locked(path, db_path=db, backtests_dir=backtests) is False

    insert_cohort_run(
        {
            "universe_version": "universe-v1",
            "ticker": "000001",
            "trade_date": "2026-09-23",
            "status": "success",
            "trigger_time": "2026-09-23T18:05:00",
        },
        db_path=db,
    )
    assert is_locked(path, db_path=db, backtests_dir=backtests) is True


def test_lock_uses_prereg_column_when_schema_has_one(tmp_path):
    """未来 schema 真加了预登记路径列 → 按列匹配(别的版本读数不得误锁本版本)。"""
    path = tmp_path / "2026-09-23-outcome-x.md"
    path.write_text("- 主指标: x", encoding="utf-8")
    db = tmp_path / "sessions.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE cohort_runs (run_id TEXT PRIMARY KEY, status TEXT, prereg_path TEXT)"
    )
    conn.execute(
        "INSERT INTO cohort_runs VALUES ('a', 'success', '/elsewhere/2026-01-01-outcome-y.md')"
    )
    conn.commit()
    conn.close()

    assert is_locked(path, db_path=db, backtests_dir=tmp_path / "bt") is False

    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO cohort_runs VALUES ('b', 'success', ?)", (path.as_posix(),))
    conn.commit()
    conn.close()
    assert is_locked(path, db_path=db, backtests_dir=tmp_path / "bt") is True


def test_lock_reads_default_db_from_env(tmp_path, monkeypatch):
    """db_path 缺省 → SESSIONS_DB_PATH(conftest 逐用例已隔离为 tmp 库)。"""
    monkeypatch.setenv("SESSIONS_DB_PATH", str(tmp_path / "env-sessions.db"))
    path = tmp_path / "2026-09-23-outcome-x.md"
    path.write_text("- 主指标: x", encoding="utf-8")
    init_cohort_runs()
    insert_cohort_run(
        {
            "universe_version": "universe-v1",
            "ticker": "600519",
            "trade_date": "2026-09-23",
            "status": "success",
            "trigger_time": "2026-09-23T18:00:00",
        }
    )
    assert is_locked(path, backtests_dir=tmp_path / "bt") is True


# ── 4. 当前旋钮(只读)──


def test_current_knobs_matches_caliber_module():
    import evals.outcome.caliber as caliber

    knobs = current_knobs()
    assert tuple(knobs) == KNOB_KEYS
    assert knobs == {key: getattr(caliber, key) for key in KNOB_KEYS}
    assert knobs["LEAKAGE_PROBE_THRESHOLD"] == 0.6


# ── 5. write_caliber_draft:只出草稿,不碰台账与常量 ──


def test_caliber_draft_does_not_touch_ledger_or_constants(tmp_path):
    """红线:草稿生成前后 ``metrics.md`` 与 ``caliber.py`` 逐字节不变。"""
    ledger_before = LEDGER.read_bytes()
    caliber_before = CALIBER_MODULE.read_bytes()

    draft = write_caliber_draft(
        {"LEAKAGE_PROBE_THRESHOLD": 0.55}, changes_dir=tmp_path / "changes", ts="20260924-120000"
    )

    assert draft == tmp_path / "changes" / "ops-caliber-draft-20260924-120000"
    assert draft.is_dir()
    assert LEDGER.read_bytes() == ledger_before
    assert CALIBER_MODULE.read_bytes() == caliber_before


def test_caliber_draft_files_are_the_three_required_artifacts(tmp_path):
    draft = write_caliber_draft(
        {"LEAKAGE_PROBE_THRESHOLD": 0.55, "MIN_SETTLED_FOR_WINRATE": 12},
        changes_dir=tmp_path,
        ts="20260924-120000",
    )
    assert sorted(p.relative_to(draft).as_posix() for p in draft.rglob("*") if p.is_file()) == [
        "metrics-timeline-line.md",
        "proposal.md",
        "specs/evaluation/spec.md",
    ]


def test_proposal_lists_old_new_per_knob_and_delta_disclaimer(tmp_path):
    draft = write_caliber_draft(
        {"LEAKAGE_PROBE_THRESHOLD": 0.55, "MIN_SETTLED_FOR_WINRATE": 12},
        changes_dir=tmp_path,
        ts="t1",
    )
    proposal = (draft / "proposal.md").read_text(encoding="utf-8")
    assert "LEAKAGE_PROBE_THRESHOLD" in proposal
    assert "0.6" in proposal and "0.55" in proposal  # 现值 → 建议值
    assert "MIN_SETTLED_FOR_WINRATE" in proposal
    assert "10" in proposal and "12" in proposal
    assert "生效须走 delta 流程" in proposal
    assert "docs/evals/metrics.md" in proposal  # 明示生效路径(先改台账 §1)


def test_spec_skeleton_is_modified_requirement(tmp_path):
    draft = write_caliber_draft({"NEUTRAL_BAND": 0.03}, changes_dir=tmp_path, ts="t1")
    skeleton = (draft / "specs" / "evaluation" / "spec.md").read_text(encoding="utf-8")
    assert "## MODIFIED Requirements" in skeleton
    assert "### Requirement: Outcome 收益指标口径与预登记" in skeleton
    assert "NEUTRAL_BAND" in skeleton
    assert "Previously" in skeleton


def test_timeline_line_draft_mentions_switchpoint(tmp_path):
    draft = write_caliber_draft({"NEUTRAL_BAND": 0.03}, changes_dir=tmp_path, ts="t1")
    line = (draft / "metrics-timeline-line.md").read_text(encoding="utf-8")
    assert "切点" in line
    assert "NEUTRAL_BAND" in line and "0.03" in line
    assert "metrics.md" in line and "§2" in line


def test_second_draft_for_same_knob_refused(tmp_path):
    changes = tmp_path / "changes"
    first = write_caliber_draft({"NEUTRAL_BAND": 0.03}, changes_dir=changes, ts="a")
    with pytest.raises(DraftExists, match="NEUTRAL_BAND"):
        write_caliber_draft({"NEUTRAL_BAND": 0.03}, changes_dir=changes, ts="b")
    assert sorted(p.name for p in changes.iterdir()) == [first.name]


def test_draft_overlapping_any_knob_refused(tmp_path):
    """新草稿只要与既有草稿**任一**旋钮重叠即拒绝(逐旋钮比对,非整表相等)。"""
    write_caliber_draft(
        {"NEUTRAL_BAND": 0.03, "PRIMARY_WINDOW_DAYS": 25}, changes_dir=tmp_path, ts="a"
    )
    with pytest.raises(DraftExists, match="PRIMARY_WINDOW_DAYS"):
        write_caliber_draft({"PRIMARY_WINDOW_DAYS": 30}, changes_dir=tmp_path, ts="b")


def test_draft_for_other_knob_allowed(tmp_path):
    first = write_caliber_draft({"NEUTRAL_BAND": 0.03}, changes_dir=tmp_path, ts="a")
    second = write_caliber_draft({"LEAKAGE_PROBE_THRESHOLD": 0.5}, changes_dir=tmp_path, ts="b")
    assert first.is_dir() and second.is_dir() and first != second


def test_draft_never_overwrites_existing_draft_dir(tmp_path):
    """同一 ts 已有草稿目录 → 拒绝,既有内容逐字节保留。"""
    draft = write_caliber_draft({"NEUTRAL_BAND": 0.03}, changes_dir=tmp_path, ts="same")
    body = (draft / "proposal.md").read_text(encoding="utf-8")
    with pytest.raises(DraftExists):
        write_caliber_draft({"LEAKAGE_PROBE_THRESHOLD": 0.5}, changes_dir=tmp_path, ts="same")
    assert (draft / "proposal.md").read_text(encoding="utf-8") == body


def test_unknown_knob_refused(tmp_path):
    changes = tmp_path / "changes"
    with pytest.raises(ValueError, match="NOT_A_KNOB"):
        write_caliber_draft({"NOT_A_KNOB": 1}, changes_dir=changes, ts="a")
    assert changes.is_dir() is False  # 连目录都不建


def test_additional_prereg_fields_are_rendered_and_kept(tmp_path):
    """额外字段(非门禁字段)也落盘并可被门禁解析器读到——不吞用户输入。"""
    path = save_prereg_version(
        {**VALID_FIELDS, "备注": "由运维控制台保存"}, dir=tmp_path, today="2026-09-24"
    )
    found = assert_preregistered(
        tmp_path, name_contains="outcome", required_fields=OUTCOME_REQUIRED_FIELDS
    )
    assert path == found.path
    assert found.fields["备注"] == "由运维控制台保存"


def test_default_stamp_is_unique_when_two_drafts_same_second(tmp_path):
    """未指定 ts(界面路径):同一秒内两次不同旋钮的草稿不得互相顶掉(各自成目录)。"""
    first = write_caliber_draft({"NEUTRAL_BAND": 0.03}, changes_dir=tmp_path)
    second = write_caliber_draft({"LEAKAGE_PROBE_THRESHOLD": 0.55}, changes_dir=tmp_path)
    assert first != second and first.is_dir() and second.is_dir()
    assert len(list(tmp_path.glob("ops-caliber-draft-*"))) == 2


class TestDraftLocationOutsideOpenspecChanges:
    """草稿落点必须在 openspec/changes 之外。

    变异实证：把 ``CHANGES_DIR`` / ``ops_api.CALIBER_CHANGES_DIR`` 改回
    ``openspec/changes`` → 本用例 RED（并使仓库级 `openspec validate --all --strict`
    由 56/0 变 56/1：骨架草稿会被当成正式 change 校验）。
    """

    def test_default_draft_dir_is_outside_openspec_changes(self):
        from finance_agent.outcome.ops import prereg as mod

        assert not mod.CHANGES_DIR.as_posix().startswith("openspec/changes")

    def test_api_default_draft_dir_is_outside_openspec_changes(self):
        from finance_agent import ops_api

        assert not ops_api.CALIBER_CHANGES_DIR.as_posix().startswith("openspec/changes")
