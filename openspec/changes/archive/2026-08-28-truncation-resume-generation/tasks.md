# Tasks — 截断续写（llm-output-resume）

参考：`specs/llm-output-resume/spec.md`（行为契约）、`design.md`（D1-D5 决策）。
测试统一放 `tests/llm/`，按 TDD「先红后绿」。

## 1. 续写请求构造器

- [x] 1.1 在 `litellm_adapter.py` 新增 `build_resume_kwargs(request_kwargs: dict, prior_text: str, progress_annotation: str | None = None) -> dict`：基于原 request_kwargs 克隆，messages 追加续写指令段（明确「不重复已给内容、无缝继续」），max_tokens 取剩余配额 `max(1, 原预算 - prior_text 估算消耗)`；为 None 的 key 保留原语义。`progress_annotation` 非 None 时把进度标注（✅/⏳/⬜）拼入续写指令段，None 时仅尾部。写失败测试（断言 messages 尾段含续写指令、max_tokens 缩小、其余 kwargs 不变）后实现（**已实现** commit bc9b387）
- [x] 1.2 在 `gateway.py` 新增 `_maybe_resume_text(finish: str, answer: str, *resume_kwargs) -> bool` 判定逻辑：`finish=="length"` 且 `answer` 非空 → True（触发续写）；其余 False。写失败测试覆盖「length+空正文→False」「stop→False」「length+非空→True」
- [x] 1.3 新增 `partial_json_progress(text: str, top_fields: list[str]) -> dict[str, str] | None`（放 `llm/contracts.py`，与既有 `extract_json` 同族）：对已生成正文做尽力部分解析，返回「顶层字段名 → done/in_progress/pending」映射；无法解析（非 JSON/空）返回 None → 调用方降级仅尾部。顶层字段清单由调用方 schema 传入。写失败测试覆盖「JSON 字段中途截断→in_progress 正确标记」「数组元素中途截断→in_progress 指向数组字段」「括号不配平不可恢复→None（降级）」

## 2. 同步路径续写（complete_text / complete_stream）

- [x] 2.1 `complete_text`（非流式）检测 `finish_reason=length` 时，用保留的已产 answer + `build_resume_kwargs` 发起一次续写 completion，追加正文并返回拼接结果；续写仍 length → 抛 `OutputTruncatedError`。TDD：mock 两次原始响应（第一次 length、第二次 stop），断言返回为两段拼接、生成调用发生两次
- [x] 2.2 `complete_stream`（同步流式）在 `classify_outcome` 前拦截 length：以已有 `_answer` 构造续写请求，续写段以 text 事件继续 yield（无 `finished` 前插），最终 yield `finished(finish_reason=续写段 reason)`；续写仍 length → 走既有 error 事件 + `_gen.update(truncated=true)`。TDD：mock chunk 流「前段 length + 续写 stop」，断言事件序列为 text…text…finished 且无重复头
- [x] 2.3 观测追加：续写发生时 `_gen.update(metadata={**existing, "resume_count": 1})`；续写仍截断补 `truncated=true`。TDD：断言 update 调用的 metadata 含 resume_count/truncated

## 3. 异步路径续写（complete_stream_async）

- [x] 3.1 `complete_stream_async` 的 `finish=="length"` 分支改为：正文非空 → 构造续写请求并递归 yield 续写段事件（text→finished），跳过「静默 finished(None)」；正文为空 → 抛 `OutputTruncatedError`（与同步语义对齐）。TDD：mock 异步 chunk 流「前段 length + 续写 stop」，断言事件顺序与拼接正确
- [x] 3.2 续写仍 length → 抛 `OutputTruncatedError` 且观测 `truncated=true`；断言干净修复了「quick 截断被当正常结束」的静默问题（新增失败用例：无续写兜底时空正文 length 必须抛错而非 finished(None)）

## 4. 集成与回归

- [x] 4.1 全量后端测试通过：`uv run pytest tests/ -m "not live"`（含既有 gateway/_llm_utils/evals 用例不回归）
- [x] 4.2 `uv run ruff check` / `uv run mypy` 通过（新增模块零告警）
- [x] 4.3 手工验证（可选，数据源可达时）：deep 节点真实触发截断 → 续写完成、Langfuse generation 可见 `resume_count=1`、`reports/` 导出完整报告 —— 数据源当前不可达，按「可选」跳过；自动化证据与后续待补项见 `tests/validation/2026-08-28-truncation-resume-generation-validation.md`

## 5. 文档收尾

- [x] 5.1 确认 `_llm_utils.py:266` 现有 32768 翻倍重试保留为 fallback 的兼容说明（不改代码，只核对行为树：续写优先、翻倍兜底）
- [x] 5.2 delta 自检：`openspec validate --change truncation-resume-generation` 通过；tasks 全勾后可申请 apply