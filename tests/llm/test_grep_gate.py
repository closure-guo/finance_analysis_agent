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

# 5.1-C 收紧后白名单：仅 adapter（litellm 唯一入口；设计档案 §8）。
# legacy.py / harness 已薄壳化转调 gateway，不再允许直接 import litellm。
_ALLOWLIST = {
    Path("llm/adapters/litellm_adapter.py"),
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
