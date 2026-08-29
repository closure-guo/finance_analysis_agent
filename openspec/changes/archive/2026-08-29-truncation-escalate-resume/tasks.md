# Tasks: truncation-escalate-resume

- [x] call_llm_streaming 截断升级分支改续写：携带首轮正文尾部 + 翻倍剩余配额，返回两轮拼接（单测覆盖：续写请求形态 / 两轮截断上抛 / 空正文全额预算 / 非截断重试不受影响）
- [x] 全量验证：uv run pytest / ruff check / mypy 通过
