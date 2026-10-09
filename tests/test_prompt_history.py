"""fix-prompt-sync-direction（issue #228）：prompt 文件 git 历史版本命中判定。

「Langfuse 回退/落后」的操作定义：remote 内容 == 该文件任一历史已提交版本
（CRLF 归一比对）——纯陈旧、无 UI 独有内容。此判定是 sync_prompts 拒收编与
deploy_prompts 预检放行的共用原语。tmp git 仓库实证。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from scripts.prompt_history import match_historical_content


def _git(args: list[str], cwd: Path) -> str:
    return subprocess.run(  # noqa: S603 - 固定参数 git 命令,无外部输入
        ["git", *args],  # noqa: S607 - git 走 PATH 解析,无外部输入
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """tmp git 仓库：prompt.md 两个历史版本（v1 → v2=HEAD）。"""
    prompts = tmp_path / "src" / "finance_agent" / "prompts"
    prompts.mkdir(parents=True)
    f = prompts / "prompt_a.md"
    f.write_text("v1 内容\n", encoding="utf-8")
    _git(["init"], tmp_path)
    _git(["config", "user.email", "t@t"], tmp_path)
    _git(["config", "user.name", "t"], tmp_path)
    _git(["add", "-A"], tmp_path)
    _git(["commit", "-m", "v1"], tmp_path)
    f.write_text("v2 内容\n", encoding="utf-8")
    _git(["add", "-A"], tmp_path)
    _git(["commit", "-m", "v2"], tmp_path)
    return tmp_path, "src/finance_agent/prompts/prompt_a.md"


class TestMatchHistoricalContent:
    def test_hit_old_version_returns_sha(self, repo):
        root, rel = repo
        sha = match_historical_content(root, rel, "v1 内容\n")
        assert sha is not None
        assert sha == _git(["log", "--format=%H", "--skip=1", "-n", "1", "--", rel], root)

    def test_hit_head_returns_sha(self, repo):
        root, rel = repo
        sha = match_historical_content(root, rel, "v2 内容\n")
        assert sha == _git(["rev-parse", "HEAD"], root)

    def test_ui_unique_content_returns_none(self, repo):
        root, rel = repo
        assert match_historical_content(root, rel, "UI 独有编辑\n") is None

    def test_untracked_file_returns_none(self, repo):
        root, _ = repo
        assert (
            match_historical_content(root, "src/finance_agent/prompts/never_committed.md", "任意\n")
            is None
        )

    def test_crlf_normalized_hit(self, repo):
        root, rel = repo
        assert match_historical_content(root, rel, "v1 内容\r\n") is not None


class TestScriptModeImports:
    """直跑回归（issue #228 冒烟实测）：`python scripts/x.py` 模式下 sys.path
    含 scripts/ 自身而非仓库根，`from scripts.prompt_history import ...` 会
    ModuleNotFoundError——双模导入须在两个脚本中都兜住。"""

    @pytest.mark.parametrize("script", ["sync_prompts.py", "deploy_prompts.py"])
    def test_help_runs_in_script_mode(self, script):
        root = Path(__file__).resolve().parents[1]
        r = subprocess.run(  # noqa: S603 - 固定脚本路径,无外部输入
            ["uv", "run", "python", f"scripts/{script}", "--help"],  # noqa: S607
            cwd=root,
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, f"{script} 直跑失败: {r.stderr[-300:]}"
