"""批量部署本地 prompts/*.md 到 Langfuse production label（ADR-0016）。

正式部署入口：本地 .md（git 跟踪）是提示词唯一权威源，Langfuse 为部署产物。
修改 prompt 后必须执行本脚本发布，否则 eval 门禁（_verify_prompt_sync）会拒绝运行。

用法：
    uv run python scripts/deploy_prompts.py
    uv run python scripts/deploy_prompts.py --dry-run
    uv run python scripts/deploy_prompts.py --exclude quick_mode

前提：已设置环境变量 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST。
若同名 prompt 已存在，Langfuse 会自动作为新版本添加（不会报错）。

可选 --labels 指定标签（默认 production）。
可选 --exclude 指定不导入的 prompt 名（不含 .md）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "src" / "finance_agent" / "prompts"

DEFAULT_EXCLUDE: set[str] = set()


def _normalize(text: str) -> str:
    """CRLF/LF 归一(口径同 evals.run._verify_prompt_sync / sync_prompts)。"""
    return text.replace("\r\n", "\n")


def _is_not_found(e: Exception) -> bool:
    s = str(e).lower()
    return "404" in s or "not found" in s or "does not exist" in s


def precheck(client, files: list[Path], exclude: set[str]) -> tuple[list[str], list[str]]:
    """发布预检(add-prompt-hot-reload):Langfuse 领先(UI 编辑未收编)则拒绝盲推。

    返回 (mismatched, unreachable)。prompt 在 Langfuse 不存在(404)视为首部属,
    不拦;拉取失败(网络/凭证)保守归 unreachable。CRLF 归一后逐字比对。
    """
    mismatched: list[str] = []
    unreachable: list[str] = []
    for f in files:
        name = f.stem
        if name in exclude:
            continue
        try:
            local = _normalize(f.read_text(encoding="utf-8"))
        except OSError:
            continue
        try:
            remote = _normalize(str(getattr(client.get_prompt(name), "prompt", "")))
        except Exception as e:  # noqa: BLE001
            if not _is_not_found(e):
                unreachable.append(name)
            continue
        if local != remote:
            mismatched.append(name)
    return mismatched, unreachable


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="导入本地 prompt 到 Langfuse")
    p.add_argument("--dry-run", action="store_true", help="只打印不导入")
    p.add_argument("--labels", default="production", help="标签，逗号分隔（默认 production）")
    p.add_argument("--exclude", nargs="*", default=list(DEFAULT_EXCLUDE), help="不导入的 prompt 名")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    labels = [s.strip() for s in args.labels.split(",") if s.strip()]
    exclude = set(args.exclude)

    files = sorted(PROMPTS_DIR.glob("*.md"))
    if not files:
        print(f"[ERROR] 未找到 prompt 文件: {PROMPTS_DIR}", file=sys.stderr)
        return 1

    print(f"发现 {len(files)} 个 prompt 文件，排除 {len(exclude)} 个")
    print(
        f"目标 Langfuse: {__import__('os').environ.get('LANGFUSE_HOST', 'http://localhost:3000')}"
    )
    print(f"标签: {labels}\n")

    if args.dry_run:
        from langfuse import Langfuse

        for f in files:
            name = f.stem
            tag = "  [SKIP 排除]" if name in exclude else "  [IMPORT]"
            print(f"  {name}{tag}")
        print("\n[dry-run] 未实际导入")
        return 0

    try:
        import os

        from langfuse import Langfuse

        client = Langfuse(
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
            host=os.environ.get("LANGFUSE_HOST", "http://localhost:3000"),
        )
    except KeyError as e:
        print(f"[ERROR] 缺少环境变量: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[ERROR] Langfuse 初始化失败: {e}", file=sys.stderr)
        return 1

    # 预检(add-prompt-hot-reload):Langfuse 领先/不可达时拒绝整批发布,
    # 防止本地盲推创建新版本抢走 production 标签覆盖 UI 编辑。
    mismatched, unreachable = precheck(client, files, exclude)
    if mismatched or unreachable:
        for name in mismatched:
            print(
                f"  [预检拦截] {name}  Langfuse production 与本地不一致(UI 编辑未收编?)",
                file=sys.stderr,
            )
        for name in unreachable:
            print(f"  [预检拦截] {name}  Langfuse 拉取失败(保守拒绝)", file=sys.stderr)
        print(
            "\n[ERROR] 预检未通过,已拒绝发布。Langfuse 侧有变更时先执行: "
            "uv run python scripts/sync_prompts.py --once 收编后再发布",
            file=sys.stderr,
        )
        return 1

    ok, skip, fail = 0, 0, 0
    for f in files:
        name = f.stem
        if name in exclude:
            print(f"  SKIP  {name}  (排除)")
            skip += 1
            continue
        try:
            content = f.read_text(encoding="utf-8")
            client.create_prompt(
                name=name,
                type="text",
                prompt=content,
                labels=labels,
            )
            print(f"  OK    {name}  ({len(content)} chars)")
            ok += 1
        except Exception as e:
            print(f"  FAIL  {name}  ({e})", file=sys.stderr)
            fail += 1

    client.flush()
    print(f"\n完成: 导入 {ok}, 跳过 {skip}, 失败 {fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
