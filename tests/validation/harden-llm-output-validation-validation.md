# 验证报告：LLM 输出校验加固（issue #36）

- **Change**: `harden-llm-output-validation`
- **验证日期**: 2026-08-03
- **关联 issue**: #36
- **前置**: #34（e2e 断言 revise 写错）已修复关闭，本次是其调查中暴露的独立缺陷

## 修复的三个缺陷

### 缺陷 1：Fund Manager 决策无枚举校验（核心）

`nodes/fund_manager.py:19` 用 `data["decision"]` 裸取键，而 `routing.py:25` 的 else 分支把任何非 `return` 的值放行到 `generate_report`，形成「LLM 直供 → 无校验 → 驱动路由 → 兜底放行」的完整静默失败链路。

修复：新增 `FundManagerDecision` 模型（`Literal["approve","reject","return"]` + `field_validator` 归一化），节点改用 `model_validate`；`state.py:96` 改 `Literal`。

### 缺陷 2：Analyst 解析降级完全静默

`nodes/analysts.py:45-56` 的 catch-all 降级产出 `claims=[]`，而零 claim 使引用校验 `all_passed=True`（`citation.py:66` 的 `failed == 0`）——解析失败反而让校验「通过」。

修复：降级与 `claim_type`/`source_type` 改写均补 WARNING 日志；`AnalystReport` 新增 `parse_degraded` 标记。

### 缺陷 3：模型字段约束只存在于注释

`models.py` 的 `DebateMessage.role`（7 值）、`confidence`（0-1）、`round` 的约束仅写在注释里，LLM 串角色或返回百分数置信度不会被发现。

修复：`role` 改 `Literal`、`confidence` 加 `Field(ge=0, le=1)`、`round` 加 `Field(ge=1)`。

### 附带：Reject 报告标注（ADR-0011:67 兑现）

ADR 规定 Reject 应「报告标注未通过审批」，但 `report.py:292` 只输出 `**reject**`。修复为 `_FUND_MANAGER_ANNOTATIONS` 中文标注映射表，未命中回退原始值以容忍历史数据。

## BREAKING 行为变更实测

本次最核心的变更是「非法决策值从静默降级为 approve 改为抛错中断」。直接验证：

```
=== 加固后 ===
  'revise'     -> ValidationError（管线中断，不静默降级）
  '拒绝'        -> ValidationError（管线中断，不静默降级）
  'REJECT'     -> 校验通过 decision='reject' 路由=generate_report
  'approve'    -> 校验通过 decision='approve' 路由=generate_report

=== 对比加固前（裸取键）===
  'revise'     若透传到 state -> 路由=generate_report（等同于 approve 放行）
  '拒绝'        若透传到 state -> 路由=generate_report（等同于 approve 放行）
```

结论：非法值被显式拦截；大小写容错（`REJECT` -> `reject`）按设计生效，不做同义词映射（`revise` 不映射为 `return`）。

## 自动化测试结果

| 范围 | 结果 |
|---|---|
| 后端全量 `uv run pytest` | **605 passed**（569 基线 + 36 新增），零失败 |
| `ruff check`（改动文件） | All checks passed |
| `ruff format --check`（改动文件） | 87 files already formatted |
| `mypy`（改动的 5 个源文件） | 零错误 |
| stub 管线 `tests/test_pipeline_stub.py` | 17 passed（stub 输出在新校验下全部合法）|
| citation retry 回归 | 24 passed（降级标记未影响 `citation_pass` 与路由）|

新增测试覆盖（异常路径此前为零）：

- `tests/nodes/test_fund_manager.py` — 非法值（5 参数化）、缺键、大小写归一化（7 参数化）、reject 用例
- `tests/nodes/test_analysts.py` — 降级 WARNING、降级标记、正常解析无标记、`claim_type`/`source_type` 改写 WARNING
- `tests/test_models.py` — `FundManagerDecision` 全套、role 7 值与非法值、confidence 越界与边界、round 范围
- `tests/nodes/test_debate.py` / `test_risk.py` — 节点级非法 role、Risk Judge 百分数置信度

## 关键设计取舍：降级标记不触发 citation retry

`docs/incidents/006-citation-infinite-loop-20260716.md` 记录过 `citation_pass=False` 触发无限 retry 的事故（根因之一是 LLM 产出的 `field_ref` 与 state schema 常不匹配）。

因此**未**让降级使 `citation_pass` 变 False：每次 retry 是一轮完整的分析师 LLM 调用（实测单轮 100s+），而解析失败源于输出格式问题，重试同一 prompt 未必能修复，代价是 3 轮昂贵调用换来仍是降级报告。

降级标记仅用于**可观测性**（WARNING 日志 + `parse_degraded` 字段），不改变图的走向。已用 24 项测试验证 `citation_pass` 判定与 `after_citation` 路由未受影响。

**有意接受的后果**：「解析失败导致的零 claim」仍会使 `all_passed=True`。取舍是用可观测性换管线稳定性，后续可依据 Langfuse 降级率数据再评估。

## Prompt 同步加固

代码加 `Literal` 后，若 prompt 引导 LLM 输出非法值会从「静默透传」变为「管线失败」。故同步加固 6 个 prompt：

- `sentiment_analyst.md:42` — `claim_type: textual` 改为 `entity`（`textual` 不在合法集内，此前导致舆情 claims 被系统性静默改写）
- `trader.md` / `risk_judge.md` — 补「confidence 必须是 0 到 1 之间的小数，不要用百分数」
- `bull_debater.md` / `bear_debater.md` / `risk_debater.md` — 补「role 必须原样输出，不要改写或翻译；round 为大于 0 的整数」

前置核对结论（Task 0）：

- 仅 3 个 prompt 产出 `DebateMessage`，role 值（`bull`/`bear`/注入的 `aggressive`/`conservative`/`neutral`）均在 7 值集内 —— `Literal` 改动安全
- `_llm_utils.py:45-51` 的 5 个 stub role、`round=1`、`confidence=0.6` 均合法
- 666 条历史会话的 `fund_manager_decision` 全为空，无历史非法值；但映射表仍保留未命中回退

## 已知 pre-existing 问题（非本次引入）

`uv run mypy src/finance_agent` 有 75 个错误，集中在 `agent_factory.py` 等未触碰文件。已用 `git stash` 隔离验证：**改动前后均为 75 errors**，本次未引入新的类型错误，且改动的 5 个源文件零错误。

`tests/scripts/` 下 4 个 lint 错误（F541/I001/UP028）同属既有调试脚本的预存问题。

## 未完成项

- **6.5 人工验证（真实 LLM 全栈）**：需启动全栈执行完整深度分析，确认 Layer V 正常审批出报告、报告显示中文标注、Langfuse 无枚举校验异常。单次约 5 分钟。
- 可选项 7.1（简化 `api.py:347-353`）与 7.2（Langfuse 违约率 score）按 design Open Questions 倾向不做。
