"""add-prompt-hot-reload Task 3:deploy_prompts 预检护栏（防本地盲推覆盖 UI 编辑）。

判别式以 git HEAD 为基准:
- remote == local → 一致放行
- remote == HEAD → 本地领先(正常待发布)放行
- remote != HEAD 且 != local → Langfuse 领先(UI 编辑未收编)拒绝
- HEAD 未知 → 保守拒绝任何差异
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts.deploy_prompts import _blocked_by_precheck, precheck


def _client(mapping: dict[str, str]):
    class _Client:
        def get_prompt(self, name: str):
            if name not in mapping:
                raise Exception("404 not found: prompt does not exist")
            return SimpleNamespace(prompt=mapping[name])

    return _Client()


def _files(tmp_path, contents: dict[str, str]) -> list[Path]:
    out = []
    for name, text in contents.items():
        p = tmp_path / f"{name}.md"
        p.write_text(text, encoding="utf-8", newline="")
        out.append(p)
    return out


def test_langfuse_ahead_detected(tmp_path):
    """UI 编辑未收编:remote 既非本地也非 HEAD → 拒绝。"""
    files = _files(tmp_path, {"alpha": "alpha 新版\n"})
    mismatched, unreachable, identical, stale = precheck(
        _client({"alpha": "alpha UI 编辑版\n"}),
        files,
        set(),
        head_contents={"alpha": "alpha 旧版\n"},
    )
    assert mismatched == ["alpha"]
    assert unreachable == []


def test_normal_local_edit_deploy_passes(tmp_path):
    """正常发布流:本地已改、Langfuse 仍在上次提交状态(remote==HEAD) → 放行。"""
    files = _files(tmp_path, {"alpha": "alpha 新版\n"})
    mismatched, unreachable, identical, stale = precheck(
        _client({"alpha": "alpha 旧版\n"}),
        files,
        set(),
        head_contents={"alpha": "alpha 旧版\n"},
    )
    assert mismatched == [] and unreachable == []


def test_consistent_passes(tmp_path):
    files = _files(tmp_path, {"alpha": "alpha 同版\n"})
    mismatched, unreachable, identical, stale = precheck(
        _client({"alpha": "alpha 同版\n"}), files, set(), head_contents={"alpha": "alpha 同版\n"}
    )
    assert mismatched == [] and unreachable == []


def test_crlf_normalized(tmp_path):
    files = _files(tmp_path, {"alpha": "a\r\nb\r\n"})
    mismatched, _, identical, _s = precheck(
        _client({"alpha": "a\nb\n"}), files, set(), head_contents={"alpha": "a\nb\n"}
    )
    assert mismatched == []


def test_head_unknown_conservative(tmp_path):
    """HEAD 未知(未跟踪/无 git):任何差异保守拒绝。"""
    files = _files(tmp_path, {"alpha": "a 新\n"})
    mismatched, _, identical, _s = precheck(
        _client({"alpha": "a 旧\n"}), files, set(), head_contents={}
    )
    assert mismatched == ["alpha"]


def test_missing_in_langfuse_ok_for_first_deploy(tmp_path):
    files = _files(tmp_path, {"alpha": "首部属\n"})
    mismatched, unreachable, identical, stale = precheck(
        _client({}), files, set(), head_contents={"alpha": "首部属\n"}
    )
    assert mismatched == [] and unreachable == []


def test_unreachable_rejected_conservatively(tmp_path):
    class _Broken:
        def get_prompt(self, name):
            raise RuntimeError("connection refused")

    files = _files(tmp_path, {"alpha": "x\n"})
    mismatched, unreachable, identical, stale = precheck(
        _Broken(), files, set(), head_contents={"alpha": "x\n"}
    )
    assert unreachable == ["alpha"]
    assert mismatched == []


def test_excluded_file_not_checked(tmp_path):
    files = _files(tmp_path, {"alpha": "a\n", "beta": "b\n"})
    # beta 排除:即使 Langfuse 领先也不拦
    mismatched, unreachable, identical, stale = precheck(
        _client({"alpha": "a\n", "beta": "beta UI 版\n"}),
        files,
        {"beta"},
        head_contents={"alpha": "a\n", "beta": "b\n"},
    )
    assert mismatched == [] and unreachable == []


class TestDirectionDiscrimination:
    """issue #228：预检区分「Langfuse 领先（UI 独有）」与「回退/落后（历史版本）」。"""

    def test_rollback_to_old_version_passes_as_stale(self, tmp_path):
        """remote == 历史版本（回退）→ 放行并列入 stale（发布将覆盖）。"""
        files = _files(tmp_path, {"alpha": "alpha 新版\n"})
        mismatched, unreachable, identical, stale = precheck(
            _client({"alpha": "alpha 更旧版\n"}),
            files,
            set(),
            head_contents={"alpha": "alpha 旧版\n"},
            history_matcher=lambda name, remote: remote == "alpha 更旧版\n",
        )
        assert mismatched == [] and unreachable == []
        assert stale == ["alpha"]

    def test_ui_unique_rejected_even_with_matcher(self, tmp_path):
        """remote 不命中任何历史版本（UI 独有）→ 维持拒绝。"""
        files = _files(tmp_path, {"alpha": "alpha 新版\n"})
        mismatched, _, _, stale = precheck(
            _client({"alpha": "alpha UI 独有\n"}),
            files,
            set(),
            head_contents={"alpha": "alpha 旧版\n"},
            history_matcher=lambda name, remote: False,
        )
        assert mismatched == ["alpha"]
        assert stale == []

    def test_remote_eq_head_not_stale(self, tmp_path):
        """remote == HEAD（正常待发布）→ 不列 stale、不调 matcher。"""
        calls = []
        files = _files(tmp_path, {"alpha": "alpha 新版\n"})
        mismatched, _, _, stale = precheck(
            _client({"alpha": "alpha 旧版\n"}),
            files,
            set(),
            head_contents={"alpha": "alpha 旧版\n"},
            history_matcher=lambda name, remote: calls.append(name) or True,
        )
        assert mismatched == [] and stale == []
        assert calls == []  # remote==HEAD 直接放行，无需查历史


class TestForceBypass:
    """issue #228-④：--force 显式覆盖 UI 编辑拦截，但不绕不可达保守拒绝。"""

    def test_force_bypasses_ui_edit_refusal(self):
        assert _blocked_by_precheck(["alpha"], [], force=True) is False

    def test_no_force_blocks_ui_edit(self):
        assert _blocked_by_precheck(["alpha"], [], force=False) is True

    def test_force_does_not_bypass_unreachable(self):
        assert _blocked_by_precheck(["alpha"], ["beta"], force=True) is True
        assert _blocked_by_precheck([], ["beta"], force=True) is True

    def test_clean_passes(self):
        assert _blocked_by_precheck([], [], force=False) is False
