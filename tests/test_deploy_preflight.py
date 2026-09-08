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

from scripts.deploy_prompts import precheck


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
    mismatched, unreachable = precheck(
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
    mismatched, unreachable = precheck(
        _client({"alpha": "alpha 旧版\n"}),
        files,
        set(),
        head_contents={"alpha": "alpha 旧版\n"},
    )
    assert mismatched == [] and unreachable == []


def test_consistent_passes(tmp_path):
    files = _files(tmp_path, {"alpha": "alpha 同版\n"})
    mismatched, unreachable = precheck(
        _client({"alpha": "alpha 同版\n"}), files, set(), head_contents={"alpha": "alpha 同版\n"}
    )
    assert mismatched == [] and unreachable == []


def test_crlf_normalized(tmp_path):
    files = _files(tmp_path, {"alpha": "a\r\nb\r\n"})
    mismatched, _ = precheck(
        _client({"alpha": "a\nb\n"}), files, set(), head_contents={"alpha": "a\nb\n"}
    )
    assert mismatched == []


def test_head_unknown_conservative(tmp_path):
    """HEAD 未知(未跟踪/无 git):任何差异保守拒绝。"""
    files = _files(tmp_path, {"alpha": "a 新\n"})
    mismatched, _ = precheck(_client({"alpha": "a 旧\n"}), files, set(), head_contents={})
    assert mismatched == ["alpha"]


def test_missing_in_langfuse_ok_for_first_deploy(tmp_path):
    files = _files(tmp_path, {"alpha": "首部属\n"})
    mismatched, unreachable = precheck(
        _client({}), files, set(), head_contents={"alpha": "首部属\n"}
    )
    assert mismatched == [] and unreachable == []


def test_unreachable_rejected_conservatively(tmp_path):
    class _Broken:
        def get_prompt(self, name):
            raise RuntimeError("connection refused")

    files = _files(tmp_path, {"alpha": "x\n"})
    mismatched, unreachable = precheck(_Broken(), files, set(), head_contents={"alpha": "x\n"})
    assert unreachable == ["alpha"]
    assert mismatched == []


def test_excluded_file_not_checked(tmp_path):
    files = _files(tmp_path, {"alpha": "a\n", "beta": "b\n"})
    # beta 排除:即使 Langfuse 领先也不拦
    mismatched, unreachable = precheck(
        _client({"alpha": "a\n", "beta": "beta UI 版\n"}),
        files,
        {"beta"},
        head_contents={"alpha": "a\n", "beta": "b\n"},
    )
    assert mismatched == [] and unreachable == []
