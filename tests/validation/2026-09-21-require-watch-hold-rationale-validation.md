# 人工验证报告: require-watch-hold-rationale

**日期**: 2026-09-21
**验证人**: 维护者（agent 执行，人工抽查项见 §4）
**关联 delta**: openspec/changes/require-watch-hold-rationale/
**E2E 门禁**: 不适用（非交互类变更——不改前端 UI / SSE 流式 / 会话切换 / 状态流转；specs 未断言该报告文本）

## 1. 验证范围

watch/hold（非执行动作）结构化理由契约：`inaction_reason` + `reeval_triggers` 字段、两侧一次打回回路（trader 侧 `validate_trade_prices` / 终稿侧 `risk_judge`）、报告结构化渲染、prompt 契约与发布、stub 同步。

## 2. 自动化验证（全绿）

| 项 | 命令 | 结果 |
|---|---|---|
| 全量后端测试 | `uv run pytest -q` | **3090 passed, 2 skipped**（16:50） |
| Lint | `uv run ruff check`（触碰 8 文件） | All checks passed |
| 格式化 | `uv run ruff format --check`（src/ + tests/nodes/ + test_models.py） | 138 files already formatted |
| 类型 | `uv run mypy`（models/validate/risk/report） | Success: no issues found in 4 source files |
| delta 校验 | `openspec validate require-watch-hold-rationale --strict` | is valid |
| prompt 发布一致性 | `deploy_prompts.py` + `evals.run._verify_prompt_sync` | 导入 14 / 失败 0；`mismatched: []`；trader & risk_judge = production **v28** |

既有测试更新（行为变更的对象，非改弱）：`test_risk.py::test_watch_no_price_requirement`（watch mock 补理由字段）、`test_report.py::test_watch_no_price_rows_and_trigger_hint` → `test_watch_missing_rationale_marked_unprovided`（旧占位行「见理由」断言的替换对象）。**补正**：被替换的报告用例丢掉了旧用例的「恰好一行」arity 断言（`md.count(...) == 1`）——这正是「非改弱」需要逐条核对的点；该断言已随终审 I-1 修复波恢复（`test_watch_missing_rationale_marked_unprovided` 增回 `assert md.count("- **再评估触发条件**:") == 1`），净覆盖无下降。

## 3. 真实链路验证（2026-09-21，600519 × P1 材料快照 × full 图，glm-5.3 钉定）

**命令**：pilot_runner 离线真跑（材料 `reports/ablation/p1/materials/600519.json`，`DEFAULT_QUERY`，约 20 次 LLM 调用），检查决策对象、检查键与 `generate_report` 输出。

**结果（全部符合预期）**：

1. **一次产出、无打回**：`trader_plan` 与 `final_trade_decision` 均为 watch 且携带完整结构化字段；`final_inaction_check = {"result": "pass", "note": ""}`（终稿侧回路一次通过，未触发重试）。
2. **内容质量**（触发条件可观察、可判定、带量化锚）：
   - trader：`['股价收复MA20（约1290一线）且MACD零轴上方金叉', '股价回落至1150-1180区间并出现放量止跌企稳信号', '季报营收或净利润恢复正增长，或飞天批价企稳回升']`
   - risk_judge（**基于风险辩论改写，非照抄 trader**）：3 条，其中第 1 条追加「二者同时满足，作为建仓必要条件」、第 3 条追加「若季报继续双降或批价进一步下行，则下调为规避」——分工约束（D1）在真实输出上生效。
3. **报告渲染**（`generate_report` 真实产物）：
   - `- **不行动原因**: 空头结构未破坏且无趋势反转证据：…`
   - `- **再评估触发条件**: ① …；② …；③ …`
   - `- **理由**: …`；无任何硬价格行。
4. **与取证结论呼应**：该标的正是「Trader 默认姿态 → watch」的样本；本 delta 不改动作分布，改的是该 watch 的信息含量（从「见理由」占位变为可回测的结构化条目）。

## 4. 限制与如实披露

1. **真实链路跑使用 ablation 变体图**（`build_variant_graph("full")`，trader 直连风控）——**不含 `validate_trade_prices` 节点**，故 trader 侧回路（节点执行 + 路由）未在真实图中经过。其可达性由静态证据覆盖：节点解析为公开包装器、三键均为 `build_5layer_graph()` 的真实通道（spec 审查员核）、`after_validate_trade_prices` 分支正确；行为由 10 例单测覆盖。
2. **打回回路未在真实链路触发**（LLM 一次合规）：fail→feedback→放行+标注 三态由单测钉死（含「仍缺放行+如实标注，不死循环」）。
3. **「禁止照抄 reasoning」为 prompt 软约束**：校验器只查缺失（非空），重复文本不被确定性拦截——design.md Open Questions 已留收敛路径（真实流量观测重复率，必要时合并字段）。
4. **deploy 版本噪声**：`deploy_prompts.py` 按既有设计对全部 14 个 prompt 建版，12 个未改动 prompt 产生同内容新版本（非行为变更，内容经 `_verify_prompt_sync` 逐字确认一致）。
5. 浏览器 E2E 未跑：不改前端渲染代码 / SSE / 会话切换 / 状态流转；前端以 ReactMarkdown 原样渲染 `report_markdown`（`frontend/src/App.tsx`），不做结构化解析（该行变化即普通 markdown 文本变化；前端对 `final_trade_decision` / `inaction_reason` / `reeval_triggers` 零引用）；无 E2E 断言覆盖该文本——故判非交互类。
6. **双回路次序盲点（终审 I-1）：理由重试替换终稿后价位结论不再复查**——价位块先跑、理由块后跑，理由重试换代（watch→buy 等）会使价位块的 pass/note 变成假阳性。已按 annotate-only 加固（重试为 annotate 复核，**不增任何 LLM 调用**：终稿缺价位如实改注「理由重试后终稿价位缺失」，价位重试转为非执行动作时改注「打回后改为非执行动作（价位不适用）」），并补两例测试（`test_inaction_retry_to_buy_rechecks_price_conclusion` / `test_price_retry_to_watch_annotated_as_not_applicable`）。
7. judge 材料自动携带新字段（`evals/extract.py::_serialize_decision`）——B5 可执行性维度的打分基线可能移动，属预期增益；按「同噪声下相对差异」解读，不追历史绝对分。

## 5. 结论

- [x] 全部通过，可 archive（自动化全绿 + 真实链路核心行为实证）
- [ ] 存在失败项（无）

**遗留观察项**（不阻塞 archive）：真实流量下 `inaction_reason` 与 `reasoning` 的重复率（若普遍重复→按 design Open Questions 收敛字段）。
