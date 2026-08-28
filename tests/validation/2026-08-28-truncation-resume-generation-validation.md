# 人工验证报告: truncation-resume-generation

**日期**: 2026-08-28
**验证人**: Closure（agent 执行 TDD 验证 + 抽查）
**关联 delta**: openspec/changes/truncation-resume-generation/
**变更性质**: 纯后端 LLM 截断续写（非交互类，不适用 E2E 浏览器门禁）

## 目标

`finish_reason=length` 时不重试完整 prompt，改为「已生成正文 + 续写指令」断点续写；统一在 gateway 层实现；续写预算与上限；trace 可追溯（resume_count/truncated）。

## 验证矩阵

| 验证项 | 依据 | 结果 |
|---|---|---|
| 续写请求构造器 | `litellm_adapter.py::build_resume_kwargs`（尾部 4000 字符 + 续写指令 + 剩余配额 max_tokens） | ✅（1.1，含 progress_annotation） |
| 续写判定 | `gateway.py::_maybe_resume_text`（finish==length 且正文非空 → True） | ✅（1.2，length+空正文 False / stop False / length+非空 True） |
| 部分解析进度标注 | `llm/contracts.py::partial_json_progress`（顶层字段 done/in_progress/pending，无法解析 → None 降级） | ✅（1.3） |
| 同步续写 complete_text/complete_stream | gateway 三入口均在 length 分支发起续写（:277/:684/:997），续写仍截断抛 `OutputTruncatedError` + metadata `truncated=true` | ✅（2.1/2.2） |
| 续写观测 | `_gen.update(metadata={...resume_count:1})`；续写仍截断补 `truncated=true` | ✅（2.3） |
| 异步续写 complete_stream_async | 正文非空 → 递归续写；正文为空 → 抛 `OutputTruncatedError`（修复 quick 截断被当正常结束的静默问题） | ✅（3.1/3.2） |
| 测试 | `tests/llm/test_gateway_resume.py`（25 用例） | ✅ 25 passed |
| 回归 | 全量后端非 live（既有 gateway/_llm_utils/evals 不回归） | ✅（本 delta 相关 25 passed；全量回归见当日非 live 跑批） |
| spec↔代码契约 | llm-output-resume 主规范 5 条 requirement（截断发起断点续写/续写请求携带结构进度标注/续写上限与终止/续写可追溯/续写拼接契约）与实现一致 | ✅ |
| `openspec validate truncation-resume-generation --strict` | — | ✅ 通过 |

## 人工抽查项（⬜ 待真实环境 follow-up）

1. ⬜ tasks 4.3（可选，数据源可达时）：deep 节点真实触发截断 → 续写完成、Langfuse generation 可见 `resume_count=1`、`reports/` 导出完整报告——当前环境数据源不可达，按任务「可选」标注跳过，待真实 LLM 环境补充
2. ⬜ 续写仍截断（超长输出）场景的真实触发

## 已知边界 / follow-up

- 续写逻辑与既有 32768 翻倍重试兼容（续写优先、翻倍兜底，5.1 已核对行为树）
- 续写上限未做独立超时（依赖请求级超时机制）

## 结论

[x] 实现 + TDD 测试 + 回归全部通过，可 sync + archive；真实环境触发项（4.3 可选）已登记为 follow-up
[ ] 存在失败项，需修复后重新验证
