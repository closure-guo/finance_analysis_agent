"""prompt 文件 git 历史版本命中判定（issue #228 方向判别共用原语）。

「Langfuse 回退/落后」的操作定义：remote 内容 == 该文件任一历史已提交版本
（CRLF 归一比对）——纯陈旧、无 UI 独有内容。sync_prompts 据此拒收编，
deploy_prompts 预检据此放行并标注「发布将覆盖」。
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _normalize(text: str) -> str:
    """CRLF/LF 归一(口径同 deploy_prompts/sync_prompts/evals 门禁)。"""
    return text.replace("\r\n", "\n")


def _git(args: list[str], cwd: Path) -> str:
    return subprocess.run(  # noqa: S603 - 固定参数 git 命令,无外部输入
        ["git", *args],  # noqa: S607 - git 走 PATH 解析,无外部输入
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def match_historical_content(
    repo_root: Path,
    rel_path: str,
    text: str,
    *,
    limit: int = 300,
) -> str | None:
    """text 命中该文件 git 历史任一已提交版本时返回该 commit sha，否则 None。

    逐版本 `git show <sha>:<path>` 归一比对，命中即短路。文件无 git 历史
    （未跟踪/新文件）返回 None。limit 约束扫描成本（历史版本数上限）。
    """
    target = _normalize(text)
    try:
        shas = _git(["log", "--format=%H", "-n", str(limit), "--", rel_path], repo_root).split()
    except subprocess.CalledProcessError:
        return None
    for sha in shas:
        try:
            blob = _git(["show", f"{sha}:{rel_path}"], repo_root)
        except subprocess.CalledProcessError:
            continue
        if _normalize(blob) == target:
            return sha
    return None
