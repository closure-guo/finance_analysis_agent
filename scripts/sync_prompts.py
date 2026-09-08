"""Langfuse production → 本地收编脚本（add-prompt-hot-reload Task 2）。

治理模型不变:本地 prompts/*.md(git 跟踪)是唯一权威源,Langfuse 是部署产物。
本脚本把「Langfuse UI 编辑」自动回流 git:production 与本地不一致(CRLF 归一
逐字比对,口径同 evals.run._verify_prompt_sync)时写回本地并产生仅含该 prompt
文件的提交;本地有未提交手工改动时不覆盖只告警(冲突保护)。

用法:
    uv run python scripts/sync_prompts.py --once      # 单次收编(默认)
    uv run python scripts/sync_prompts.py --dry-run   # 只报告不落盘
    uv run python scripts/sync_prompts.py --watch     # 守护(默认 30s 轮询)
    uv run python scripts/sync_prompts.py --watch --interval 60

须在 git 仓库所在宿主机运行(容器内 .md 为镜像层,回写不持久)。
前提:LANGFUSE_PUBLIC_KEY/SECRET_KEY(经 .env),LANGFUSE_HOST 默认 localhost:3000。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = REPO_ROOT / "src" / "finance_agent" / "prompts"


@dataclass
class Action:
    """单个 prompt 的收编判定。

    status: collect(需收编) / conflict(本地脏,人工裁决) / ok(一致)
            / local_only(production 无此 prompt) / remote_error(拉取失败)
    """

    name: str
    path: Path
    status: str
    remote_text: str | None = None
    version: int | str | None = None


def normalize(text: str) -> str:
    """CRLF/LF 归一(口径同 evals.run._verify_prompt_sync)。"""
    return text.replace("\r\n", "\n")


def _is_not_found(e: Exception) -> bool:
    """Langfuse『prompt 不存在』启发式判定(404/not found/does not exist)。"""
    s = str(e).lower()
    return "404" in s or "not found" in s or "does not exist" in s


def _git(args: list[str], cwd: Path) -> str:
    return subprocess.run(  # noqa: S603 - 固定参数 git 命令,无外部输入
        ["git", *args],  # noqa: S607 - git 走 PATH 解析,无外部输入
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _has_uncommitted(path: Path, repo_root: Path) -> bool:
    out = subprocess.run(  # noqa: S603 - 固定参数 git status,无外部输入
        ["git", "status", "--porcelain", "--", str(path)],  # noqa: S607 - git 走 PATH 解析
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return bool(out.strip())


def plan_actions(prompts_dir: Path, client) -> list[Action]:  # noqa: ANN001 - langfuse client
    """扫描 prompts/*.md,比对 production,产出收编动作清单(不做任何写操作)。"""
    actions: list[Action] = []
    for f in sorted(prompts_dir.glob("*.md")):
        name = f.stem
        try:
            with open(f, encoding="utf-8", newline="") as fh:
                local = normalize(fh.read())
        except OSError:
            continue
        try:
            remote_obj = client.get_prompt(name)
            remote = normalize(str(getattr(remote_obj, "prompt", "")))
            version = getattr(remote_obj, "version", None)
        except Exception as e:  # noqa: BLE001
            if _is_not_found(e):
                actions.append(Action(name, f, "local_only"))
            else:
                actions.append(Action(name, f, "remote_error"))
            continue
        if local == remote:
            actions.append(Action(name, f, "ok"))
        else:
            actions.append(Action(name, f, "collect", remote_text=remote, version=version))
    return actions


def apply_actions(
    actions: list[Action],
    repo_root: Path,
    dry_run: bool = False,
    git=_git,
) -> tuple[int, list[str]]:
    """执行收编:写回 + 限定暂存的提交。返回 (exit_code, conflicts)。

    冲突保护:目标文件 git status 非空(本地未提交改动)时不覆盖,列入 conflicts,
    exit_code=1。dry_run 只报告不落盘。
    """
    conflicts: list[str] = []
    for a in actions:
        if a.status != "collect":
            continue
        if _has_uncommitted(a.path, repo_root):
            print(f"  [CONFLICT] {a.name}  本地有未提交改动,不覆盖,需人工裁决")
            conflicts.append(a.name)
            continue
        if dry_run:
            print(f"  [DRY] 将收编 {a.name} v{a.version}({len(a.remote_text or '')} chars)")
            continue
        a.path.write_text(a.remote_text or "", encoding="utf-8")
        git(["add", str(a.path)], repo_root)
        git(
            [
                "-c",
                "core.autocrlf=false",
                "commit",
                "-m",
                f"chore(prompts): 收编 Langfuse production 变更 {a.name} v{a.version}（UI 编辑回流）",
            ],
            repo_root,
        )
        print(f"  [OK] 收编 {a.name} v{a.version} 并提交")
    for a in actions:
        if a.status == "remote_error":
            print(f"  [WARN] {a.name} Langfuse 拉取失败,本次跳过")
    return (1 if conflicts else 0), conflicts


def _build_client():
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    import os

    from langfuse import Langfuse

    return Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.environ.get("LANGFUSE_HOST", "http://localhost:3000"),
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Langfuse production → 本地收编(回写 git)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--watch", action="store_true", help="守护模式:循环收编")
    mode.add_argument("--once", action="store_true", help="单次收编(默认)")
    p.add_argument("--dry-run", action="store_true", help="只报告不落盘不提交")
    p.add_argument("--interval", type=float, default=30.0, help="守护轮询间隔秒(默认 30)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    try:
        client = _build_client()
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] Langfuse 初始化失败: {e}", file=sys.stderr)
        return 1

    if not args.watch:
        actions = plan_actions(PROMPTS_DIR, client)
        code, conflicts = apply_actions(actions, REPO_ROOT, dry_run=args.dry_run)
        n_collect = sum(1 for a in actions if a.status == "collect")
        print(f"\n完成: 待收编 {n_collect}, 冲突 {len(conflicts)}")
        return code

    print(f"[watch] 守护启动,间隔 {args.interval}s(Ctrl+C 退出)")
    try:
        while True:
            actions = plan_actions(PROMPTS_DIR, client)
            _, conflicts = apply_actions(actions, REPO_ROOT)
            if conflicts:
                print(f"[watch] {len(conflicts)} 个冲突待人工裁决: {conflicts}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[watch] 退出")
        return 0


if __name__ == "__main__":
    sys.exit(main())
