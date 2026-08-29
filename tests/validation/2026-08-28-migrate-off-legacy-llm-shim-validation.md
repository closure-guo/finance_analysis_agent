# 人工验证报告: migrate-off-legacy-llm-shim

**日期**: 2026-08-28
**验证人**: Closure（agent 执行验证 + 抽查）
**关联 delta**: openspec/changes/migrate-off-legacy-llm-shim/
**变更性质**: 纯后端重构（非交互类，不适用 E2E 浏览器门禁）

## 目标

删除 legacy 薄壳（`call_llm` / `call_llm_stream` / `call_llm_with_tools` / `legacy.py` / 顶层 `llm.py`），生产代码全部直连 gateway，单一入口、无双重语义，且「空 content 回退 reasoning」语义逐点复刻。

## 验证矩阵

| 验证项 | 依据 | 结果 |
|---|---|---|
| legacy 薄壳已删除 | `src/finance_agent/llm/legacy.py`、顶层 `src/finance_agent/llm.py` 均不存在；`llm/__init__.py` 仅 re-export `LLMConfig`（来自 `config.py`）兼容旧 import | ✅ |
| 调用方全部直连 gateway | `react_agent.py:326,397`、`events/web_fetcher.py:135`、`nodes/report.py:188` 均调 `gateway.complete_text`；流式入口 `nodes/_llm_utils.py:299` 直连 `gateway.complete_stream` | ✅ |
| 空 content 回退 reasoning 逐点复刻 | `react_agent.py:330,400`、`web_fetcher.py:139`、`report.py:197` 均为 `text or meta.get("raw_reasoning") or ""` | ✅ |
| grep 门禁 | 全库无非注释 legacy 引用（残留均为注释/文档串）；`from finance_agent.llm import call_llm*` 零命中 | ✅ |
| 后端测试 | `tests/llm/test_legacy_migration.py` + `tests/nodes/test_call_llm_streaming_gateway.py` + `tests/nodes/test_call_llm_for_json.py` + `tests/test_llm.py` | ✅ 通过 |
| spec↔代码契约 | llm-provider-gateway 主规范「litellm 适配收口」「arguments 规范化」「finish_reason 分类」等 requirement 均有对应实现（gateway/adapters） | ✅ |
| `openspec validate migrate-off-legacy-llm-shim --strict` | — | ✅ 通过 |

## 人工抽查项（⬜ 待真实环境 follow-up）

1. ⬜ 真实 LLM 调用回归：mock/stub 之外，用真实 key 各跑一次 chat + 流式，确认 gateway 直连链路产出与 legacy 时代一致（本轮以测试套件 162 passed 为自动化证据）

## 已知边界 / follow-up

- 无（重构面已由 grep 门禁 + 测试套件覆盖）

## 结论

[x] 自动化验证全部通过（测试套件 + grep 门禁 + spec 契约），可 sync + archive；真实 LLM 回归项已在「人工抽查项」登记为 follow-up
[ ] 存在失败项，需修复后重新验证
