"""add-prompt-hot-reload Task 3:deploy_prompts 预检护栏（防本地盲推覆盖 UI 编辑）。"""

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
    files = _files(tmp_path, {"alpha": "alpha 新版\n"})
    mismatched, unreachable = precheck(_client({"alpha": "alpha UI 编辑版\n"}), files, set())
    assert mismatched == ["alpha"]
    assert unreachable == []


def test_consistent_passes(tmp_path):
    files = _files(tmp_path, {"alpha": "alpha 同版\n"})
    mismatched, unreachable = precheck(_client({"alpha": "alpha 同版\n"}), files, set())
    assert mismatched == [] and unreachable == []


def test_crlf_normalized(tmp_path):
    files = _files(tmp_path, {"alpha": "a\r\nb\r\n"})
    mismatched, _ = precheck(_client({"alpha": "a\nb\n"}), files, set())
    assert mismatched == []


def test_missing_in_langfuse_ok_for_first_deploy(tmp_path):
    files = _files(tmp_path, {"alpha": "首部属\n"})
    mismatched, unreachable = precheck(_client({}), files, set())
    assert mismatched == [] and unreachable == []


def test_unreachable_rejected_conservatively(tmp_path):
    class _Broken:
        def get_prompt(self, name):
            raise RuntimeError("connection refused")

    files = _files(tmp_path, {"alpha": "x\n"})
    mismatched, unreachable = precheck(_Broken(), files, set())
    assert unreachable == ["alpha"]
    assert mismatched == []


def test_excluded_file_not_checked(tmp_path):
    files = _files(tmp_path, {"alpha": "a\n", "beta": "b\n"})
    # beta 排除:即使 Langfuse 领先也不拦
    mismatched, unreachable = precheck(
        _client({"alpha": "a\n", "beta": "beta UI 版\n"}), files, {"beta"}
    )
    assert mismatched == [] and unreachable == []
