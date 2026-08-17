# tests/llm/test_grep_gate.py
"""litellm import 收口门禁（delta Task 1.5）。

规则：src/finance_agent 内除白名单外禁止 import litellm。
白名单按迁移阶段收紧（阶段一允许存量薄壳，阶段五 Task 5.1 后移除）。
CI 经 pytest 自动执行本门禁。
"""

from __future__ import annotations

import re
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src" / "finance_agent"

# 阶段一白名单：adapter（唯一正式入口）+ 兼容薄壳存量
_ALLOWLIST = {
    Path("llm/adapters/litellm_adapter.py"),
    Path("llm/legacy.py"),  # 旧 llm.py 薄壳（Task 5.1 转调后收紧）
    Path("harness/litellm_client.py"),  # 存量 ReAct 客户端（Task 5.1 迁入 adapter）
}

_IMPORT_RE = re.compile(r"^\s*(import litellm|from litellm)", re.MULTILINE)


def test_no_litellm_import_outside_allowlist():
    violators: list[str] = []
    for py in _SRC.rglob("*.py"):
        rel = py.relative_to(_SRC).as_posix()
        if Path(rel) in _ALLOWLIST:
            continue
        if _IMPORT_RE.search(py.read_text(encoding="utf-8", errors="ignore")):
            violators.append(rel)
    assert not violators, (
        f"litellm import 越界（只允许 {sorted(str(p) for p in _ALLOWLIST)}）: {violators}。"
        "新代码必须经 finance_agent.llm.adapters.litellm_adapter 收口。"
    )
