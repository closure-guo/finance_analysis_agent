## 0. 实施前置核对（改 Literal 前必做）

- [x] 0.1 核对全部辩论 prompt 声明的 `role` 取值是否都在拟定的 `Literal` 7 值集内。结论：仅 3 个 prompt 产出 `DebateMessage`（`bull_debater.md:9` 为 `"bull"`、`bear_debater.md:9` 为 `"bear"`、`risk_debater.md:9` 为模板变量 `"{role}"` 由 `nodes/risk.py:19` 注入 `aggressive`/`conservative`/`neutral`），全部合法。另核对 `_llm_utils.py:45-51` 的 5 个 stub role 亦全部合法。`Literal` 改动安全。
- [x] 0.2 核对 `prompts/trader.md:10`（`0.75`）与 `prompts/risk_judge.md:10`（`0.6`）示例值均为小数，但**措辞未约束范围**（只写了 action 限制）。已在任务 4 中补齐「confidence 必须是 0 到 1 之间的小数，不要用百分数」。
- [x] 0.3 Langfuse production 版本核对：本地服务未启动，无法在线核对。风险已缓解——本次 prompt 改动均为**收紧措辞/修正非法枚举**，即使 Langfuse 未同步也不会恶化现状（`sentiment_analyst` 的 `textual` 在旧版下仍被静默改写为 `entity`，与加固前一致）。人工验证（6.5）时需观察 Langfuse 是否出现枚举校验异常。
- [x] 0.4 历史数据核对：`data/sessions.db` 的 666 条含 `agent_process` 记录中，`fund_manager_decision` 全部为空（多为快速模式/未走完五层管线），无历史非法值。但映射表仍保留未命中回退以容错空值与未来数据。

## 1. Fund Manager 决策枚举强校验（缺陷 1，核心）

- [x] 1.1 编写失败测试 `test_invalid_decision_raises`：参数化覆盖 `revise`/`拒绝`/`maybe`/`APPROVED`/空串，断言抛 `ValidationError`。
- [x] 1.2 编写失败测试 `test_missing_decision_key_raises`：缺 `decision` 键断言抛 `ValidationError` 而非裸 `KeyError`。
- [x] 1.3 编写失败测试 `test_decision_normalizes_case_and_whitespace`：7 组参数化覆盖 `Approve`/`APPROVE`/` approve `/`Reject`/` REJECT `/`Return`/`  RETURN  `。另加 `test_normalized_return_increments_count` 验证归一化后仍触发 `return_count` 递增。
- [x] 1.4 补齐缺失的 `test_reject_decision`：断言 `fund_manager_decision == "reject"` 且不含 `return_count` 键。
- [x] 1.5 `models.py` 新增 `FundManagerDecision`：`decision: Literal["approve","reject","return"]` + `reasoning: str = ""`，`field_validator("decision", mode="before")` 做 `strip().lower()` 归一化。
- [x] 1.6 `nodes/fund_manager.py` 改为 `FundManagerDecision.model_validate(data).decision`，移除裸取键。
- [x] 1.7 `state.py:96` 改为 `Literal["approve", "reject", "return"]`。
- [x] 1.8 `uv run pytest tests/nodes/test_fund_manager.py tests/test_routing.py tests/test_models.py` -> 35 passed。
- [x] 1.9 mypy 检查改动文件零错误。

## 2. Reject 报告标注补齐（ADR-0011:67 兑现）

- [x] 2.1 编写失败测试 `test_fund_manager_decision_chinese_annotation`：三种决策参数化断言中文标注。同步更新既有 `test_report_contains_fund_manager_decision`（原断言 `"approve" in report`，中文标注后改为断言「审批通过」）。
- [x] 2.2 编写 `test_report_tolerates_legacy_invalid_decision`：历史非法值 `"revise"` 不抛错、回退显示原始值。
- [x] 2.3 `nodes/report.py` 改为 `_FUND_MANAGER_ANNOTATIONS` 映射表（审批通过/未通过审批/已退回交易员重新评估），未命中回退原始值。
- [x] 2.4 `uv run pytest tests/nodes/test_report.py` -> 9 passed。

## 3. Analyst 解析降级可观测化（缺陷 2）

- [x] 3.1 编写失败测试 `test_malformed_json_logs_warning`：用 `caplog` 断言 WARNING 含节点名。
- [x] 3.2 编写失败测试 `test_degraded_report_carries_marker`：断言 `parse_degraded is True` 且 `claims == []`。另加 `test_successful_parse_has_no_degraded_marker` 验证正常路径不带标记。
- [x] 3.3 编写失败测试 `test_invalid_claim_type_logs_warning`：`textual` 改写为 `entity`，断言 WARNING 含原值与改写值。
- [x] 3.4 编写失败测试 `test_invalid_source_type_logs_warning`：`hearsay` 改写为 `data`，同上。
- [x] 3.5 `nodes/analysts.py` 降级路径加 WARNING（含 `agent_name` 与异常类型/信息）+ `parse_degraded=True` 标记。保留 `except Exception`——它已排除 `KeyboardInterrupt`/`SystemExit`（继承 `BaseException`），进一步收窄会漏掉真实解析失败反而让管线崩溃。
- [x] 3.6 `_sanitize_claims` 的 `claim_type`/`source_type` 改写加 WARNING，保留既有改写行为。函数签名加 `agent_name` 参数以便日志定位。
- [x] 3.7 修正 `prompts/sentiment_analyst.md:42` 的 `claim_type: textual` -> `entity（实体/事件引用）`。
- [x] 3.8 验证不触发 retry 回归：`uv run pytest tests/nodes/test_citation_node.py tests/test_routing.py tests/test_models.py` -> 24 passed，`citation_pass` 判定与 `after_citation` 路由未受影响。
- [x] 3.9 `uv run pytest tests/nodes/test_analysts.py` -> 7 passed。

## 4. DebateMessage / TradeDecision 字段约束（缺陷 3）

- [x] 4.1 编写失败测试 `test_debate_message_invalid_role_rejected` + `test_debate_message_all_legal_roles_accepted`（7 值全覆盖）。
- [x] 4.2 编写失败测试 `test_trade_decision_confidence_out_of_range_rejected`（`95`/`-0.5`/`1.5`）+ `test_trade_decision_confidence_boundaries_accepted`（`0.0`/`1.0`）。
- [x] 4.3 编写失败测试 `test_debate_message_invalid_round_rejected`（`0`/`-1`）。
- [x] 4.4 编写节点级测试 `tests/nodes/test_debate.py::TestDebateRoleValidation::test_invalid_role_raises` 与 `tests/nodes/test_risk.py::TestRiskFieldValidation`（非法 role + Risk Judge 百分数置信度）。
- [x] 4.5 `models.py` 的 `role` 改为 7 值 `Literal`。
- [x] 4.6 `models.py` 的 `confidence` 加 `Field(ge=0, le=1)`。同步加固 `prompts/trader.md` 与 `prompts/risk_judge.md` 的 confidence 措辞。
- [x] 4.7 `models.py` 的 `round` 加 `Field(ge=1)`。同步为 3 个辩论 prompt 补 role/round 约束说明，防止 LLM 串角色触发新增的 Literal 失败。
- [x] 4.8 `uv run pytest tests/test_models.py tests/nodes/test_debate.py tests/nodes/test_risk.py tests/nodes/test_trader.py` -> 24 passed。

## 5. 测试基线澄清

- [x] 5.1 为 `tests/test_routing.py` 的 `test_reject_returns_generate_report` 补 docstring：说明该基线符合 ADR-0011:67「Reject → 报告标注未通过审批」，但**不代表** reject 等价于 approve——区分由任务 2 的报告中文标注承担。未改断言本身。

## 6. 验证

- [x] 6.1 `uv run pytest` 全量 -> **605 passed**（569 基线 + 36 新增），零失败。
- [x] 6.2 `ruff check` 与 `ruff format --check`（改动文件范围）全部通过。`tests/scripts/` 下 4 个既有 lint 错误属预存，未触碰。
- [x] 6.3 `uv run mypy src/finance_agent`：改动的 5 个源文件零错误。全量 75 errors 为 pre-existing——已用 `git stash` 隔离验证改动前后同为 75 errors。
- [x] 6.4 `uv run pytest tests/test_pipeline_stub.py` -> 17 passed，stub 输出在新校验下全部合法。
- [ ] 6.5 人工验证（真实 LLM）：启动全栈执行完整深度分析，确认 Layer V 正常审批出报告、报告显示中文标注、Langfuse 上无枚举校验异常。
- [x] 6.6 负向验证（BREAKING 行为）：直接验证非法值中断而非静默放行。实测 `revise`/`拒绝` -> ValidationError；`REJECT` -> 归一化为 `reject` 通过；并对比展示加固前这两个值会被 `after_fund_manager` 路由到 `generate_report`（等同 approve 放行）。结果见 `tests/validation/harden-llm-output-validation-validation.md`。

## 7. 可选（不阻塞归档）

- [x] 7.1 决定**不简化** `api.py:347-353` 的三段 if + 兜底文案——兜底对历史非法数据与空值仍有价值（design Open Questions 的倾向）。
- [x] 7.2 决定**本次不做** Langfuse 枚举违约 score——先靠 WARNING 日志观察，避免范围扩张（design Open Questions 的倾向）。
