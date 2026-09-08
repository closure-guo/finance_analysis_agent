"""add-prompt-hot-reload Task 2:sync_prompts 收编脚本（Langfuse production → 本地 git）。

用 tmp git 仓库隔离验证：UI 编辑收编、冲突保护、一致空操作、dry-run 不落盘、
CRLF 归一口径（与 eval 门禁一致）。
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.sync_prompts import apply_actions, normalize, plan_actions


def _git(args: list[str], cwd: Path) -> str:
    return subprocess.run(  # noqa: S603 - 固定参数 git 命令,无外部输入
        ["git", *args],  # noqa: S607 - git 走 PATH 解析,无外部输入
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _fake_client(mapping: dict[str, str], versions: dict[str, int] | None = None):
    versions = versions or {}

    class _Client:
        def get_prompt(self, name: str):
            if name not in mapping:
                raise Exception("404 not found: prompt does not exist")
            return SimpleNamespace(prompt=mapping[name], version=versions.get(name, 1))

    return _Client()


@pytest.fixture
def repo(tmp_path):
    """tmp git 仓库 + prompts 目录,基线提交两个 prompt 文件。"""
    prompts = tmp_path / "src" / "finance_agent" / "prompts"
    prompts.mkdir(parents=True)
    (prompts / "alpha.md").write_text("alpha v1\n", encoding="utf-8")
    (prompts / "beta.md").write_text("beta v1\n", encoding="utf-8")
    _git(["init"], tmp_path)
    _git(["config", "user.email", "t@t"], tmp_path)
    _git(["config", "user.name", "t"], tmp_path)
    _git(["add", "-A"], tmp_path)
    _git(["commit", "-m", "baseline"], tmp_path)
    return tmp_path, prompts


def _count_commits(root: Path) -> int:
    return len(_git(["log", "--oneline"], root).splitlines())


class TestCollect:
    def test_ui_edit_collected_with_dedicated_commit(self, repo):
        root, prompts = repo
        client = _fake_client({"alpha": "alpha v2\n", "beta": "beta v1\n"}, {"alpha": 2})
        before = _count_commits(root)
        code, conflicts = apply_actions(plan_actions(prompts, client), root)
        assert code == 0 and conflicts == []
        assert (prompts / "alpha.md").read_text(encoding="utf-8") == "alpha v2\n"
        assert (prompts / "beta.md").read_text(encoding="utf-8") == "beta v1\n"  # 未动
        assert _count_commits(root) == before + 1
        # 提交只含 alpha.md
        files = _git(["show", "--name-only", "--pretty=format:", "HEAD"], root).split()
        assert files == ["src/finance_agent/prompts/alpha.md"]
        assert "alpha" in _git(["log", "-1", "--pretty=%s"], root)

    def test_crlf_normalized_consistent(self, repo):
        root, prompts = repo
        (prompts / "alpha.md").write_text("alpha v1\r\nsecond\r\n", encoding="utf-8", newline="")
        # 本地未提交改动会让收编走冲突保护,先提交
        _git(["add", "-A"], root)
        _git(["commit", "-m", "crlf"], root)
        client = _fake_client({"alpha": "alpha v1\nsecond\n", "beta": "beta v1\n"})
        actions = plan_actions(prompts, client)
        assert all(a.status == "ok" for a in actions)


class TestConflictProtection:
    def test_uncommitted_local_edit_not_overwritten(self, repo):
        root, prompts = repo
        (prompts / "alpha.md").write_text("alpha 本地未提交\n", encoding="utf-8")
        client = _fake_client({"alpha": "alpha v2\n", "beta": "beta v1\n"})
        code, conflicts = apply_actions(plan_actions(prompts, client), root)
        assert code == 1
        assert conflicts == ["alpha"]
        assert (prompts / "alpha.md").read_text(encoding="utf-8") == "alpha 本地未提交\n"


class TestNoop:
    def test_all_consistent_no_write_no_commit(self, repo):
        root, prompts = repo
        before = _count_commits(root)
        client = _fake_client({"alpha": "alpha v1\n", "beta": "beta v1\n"})
        code, conflicts = apply_actions(plan_actions(prompts, client), root)
        assert code == 0 and conflicts == []
        assert _count_commits(root) == before

    def test_local_only_and_remote_error_reported(self, repo):
        root, prompts = repo
        # gamma.md 仅本地(production 无) → local_only;拉取异常 → remote_error
        (prompts / "gamma.md").write_text("gamma\n", encoding="utf-8")
        client = _fake_client({"alpha": "alpha v1\n", "beta": "beta v1\n"})

        class _Broken:
            def get_prompt(self, name):
                if name == "alpha":
                    raise RuntimeError("conn refused")
                return _fake_client({"beta": "beta v1\n"}).get_prompt(name)

        broken = _Broken()
        actions = plan_actions(prompts, client)
        statuses = {a.name: a.status for a in actions}
        # gamma 在 mapping 无 → local_only
        assert statuses["gamma"] == "local_only"
        actions2 = plan_actions(prompts, broken)
        assert {a.name: a.status for a in actions2}["alpha"] == "remote_error"


class TestDryRun:
    def test_dry_run_no_write_no_commit(self, repo):
        root, prompts = repo
        before = _count_commits(root)
        client = _fake_client({"alpha": "alpha v2\n", "beta": "beta v1\n"})
        actions = plan_actions(prompts, client)
        code, conflicts = apply_actions(actions, root, dry_run=True)
        assert code == 0 and conflicts == []
        assert (prompts / "alpha.md").read_text(encoding="utf-8") == "alpha v1\n"  # 未写
        assert _count_commits(root) == before


def test_normalize():
    assert normalize("a\r\nb\r\n") == "a\nb\n"
    assert normalize("a\nb\n") == "a\nb\n"
