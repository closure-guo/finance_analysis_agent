"""一次性重构脚本：删除 api.py 中 analyze 端点的旧 ReAct 直连段。

删除范围：从 "走 harness ReAct Agent" 注释行到其后的 "    )"（event_stream 结尾），
保留 "# ── Streaming Chat ──" 分隔注释。删除后用 ast 解析校验语法。
"""

import ast
from pathlib import Path

path = Path("src/finance_agent/api.py")
lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

startIdx = next(i for i, line in enumerate(lines) if "走 harness ReAct Agent" in line)
streamingChatIdx = next(
    i for i, line in enumerate(lines) if line.startswith("# ── Streaming Chat ──")
)

# 从 startIdx 删到 streamingChatIdx 之前的 "    )" 行（含），保留空行分隔
endIdx = streamingChatIdx - 1
while endIdx > startIdx and lines[endIdx].strip() == "":
    endIdx -= 1
assert lines[endIdx].rstrip() == "    )", f"结尾锚点不符: {lines[endIdx]!r}"

deletedCount = endIdx - startIdx + 1
newLines = lines[:startIdx] + lines[endIdx + 1 :]
newSource = "".join(newLines)
ast.parse(newSource)  # 语法校验

path.write_text(newSource, encoding="utf-8")
print(f"删除 {deletedCount} 行（{startIdx + 1}-{endIdx + 1}），语法校验通过")
