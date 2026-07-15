"""批量导入本地 prompts/*.md 到 Langfuse（ADR-0016）。

用法：
    .venv/Scripts/python.exe tests/scripts/import_prompts_to_langfuse.py
    .venv/Scripts/python.exe tests/scripts/import_prompts_to_langfuse.py --dry-run
    .venv/Scripts/python.exe tests/scripts/import_prompts_to_langfuse.py --exclude fa_analyze ia_analyze

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

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "src" / "finance_agent" / "prompts"

DEFAULT_EXCLUDE = {"fa_analyze", "ia_analyze", "fa_summary", "ia_summary"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="导入本地 prompt 到 Langfuse")
    p.add_argument("--dry-run", action="store_true", help="只打印不导入")
    p.add_argument("--labels", default="production", help="标签，逗号分隔（默认 production）")
    p.add_argument("--exclude", nargs="*", default=list(DEFAULT_EXCLUDE), help="不导入的 prompt 名")
    p.add_argument("--include-all", action="store_true", help="导入全部，包括废弃的")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    labels = [s.strip() for s in args.labels.split(",") if s.strip()]
    exclude = set() if args.include_all else set(args.exclude)

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
            tag = "  [SKIP 废弃]" if name in exclude else "  [IMPORT]"
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

    ok, skip, fail = 0, 0, 0
    for f in files:
        name = f.stem
        if name in exclude:
            print(f"  SKIP  {name}  (废弃/排除)")
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
