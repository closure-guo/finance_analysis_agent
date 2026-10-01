# update-decision-integrity-gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 决策层完整性门禁——决策文本价位交叉校验、非法仓位档位渲染归一、buy/sell 终稿再评估触发条件必填化、FM 审批可见性与置信度语义。修复 cohort 审查确认的六类决策层失真（600845 触发价幻觉 / 601066 空洞触发 / 601818 sell 无触发条件仍获批 / 600515 非法档位透传 / 002916、600015 FM 复述失真 / 600515 置信度无解释漂移）。

**Architecture:** 全部为「可观测优先」语义——anomaly 登记 + 报告标注，不硬中断管线（FM 仲裁权保留）。价位校验复用既有 anomalies 通道；打回机制复用 `final_price_check`/`final_inaction_check` 同款一次重试语义。

**Tech Stack:** Python 3.12 / pydantic / pytest。

## Global Constraints

- **工作目录**: `.worktrees/fin-freshness-valuation`（分支 feat/fin-freshness-valuation）。
- **TDD 铁律**: 先红后绿。每个 Scenario 至少一个复现测试。
- **可观测优先**: 校验失败/anomaly SHALL NOT 硬中断管线（除非 spec 明示 ValidationError 重试后仍失败）。
- **归一不回写**: 档位归一只作用于渲染，决策对象落库/trace 保留原值。
- **Lint/类型**: ruff 全绿；mypy `uv run mypy src/` 基线 81 持平。
- **prompt 变更**: 改 fund_manager.md / risk_judge.md 后必须 `uv run python scripts/deploy_prompts.py`（set -a && source ../../.env && set +a 加载凭据）。
- **Commit**: 中文描述引用 delta 名与任务号；不 push。

---

### Task 1: 决策文本价位交叉校验器（tasks 1.1–1.4）

**Files:**
- Create: `src/finance_agent/metrics/decision_price_check.py`（纯函数模块）
- Modify: `src/finance_agent/nodes/risk.py`（risk_judge 返回 dict 增 `decision_price_anomalies` 键；在 payout self-check 之后调用）
- Test: `tests/metrics/test_decision_price_check.py`

**Interfaces:**
- Consumes: `final_trade_decision`（TradeDecision：reeval_triggers/inaction_reason/reasoning 字段）、`technical_indicators`（state 键，含 MA5/10/20/60 序列最新值等）、`price_levels`（state 键）、最新收盘价（technical_indicators 或 kline 尾行收盘）
- Produces: `check_decision_prices(decision: TradeDecision, technical_indicators: dict, price_levels: dict, latest_close: float | None) -> list[dict]`；每条 anomaly `{"kind": "deviation"|"empty_trigger", "source_text": str, "indicator": str|None, "verified_value": float|None, "deviation_pct": float|None, "message": str}`。risk_judge 返回 `decision_price_anomalies`（list），后续报告渲染消费

**行为契约（spec price-level-tooling 逐条）：**
1. 数值提取：从 reeval_triggers 每条 + inaction_reason + reasoning 中提取数值（含小数）；量纲归类——**价格量纲**（数值与 latest_close 同数量级，或紧邻 MA/高低点量级）vs **百分比/比值量纲**（带 % 后缀、或「倍/比值」上下文、或数值形态为 0-1 区间小数/超过 100 且带 %）。非价格量纲不进入价位校验（600015 的 18.35% 阈值不误报）
2. 指标归属：文本点名指标名（MA60/MA20/布林上轨等）→ 直接取对应已验证值；未点名 → 在全部已验证指标（最新收盘、MA5/10/20/60、布林上中下轨、近期高低点）中找与该数值**相对偏差最小**者
3. 偏差形态：与归属指标偏差 > 2%（常量 `_DEVIATION_THRESHOLD = 0.02`）且不在 price_levels 参考带（`price_levels` 的支撑/压力带区间内）→ deviation anomaly
4. 空洞形态：触发文本含上破词（站上/突破/收复/放量突破）且价位 ≤ latest_close，或下破词（跌破/回落至/失守）且价位 ≥ latest_close → empty_trigger anomaly
5. 正常直通：偏差 ≤ 2% 且方向语义有效 → 无 anomaly

**测试锚点（spec 四 Scenario + 600015 反例）：** 600845（18.8 vs MA60 18.066 → deviation，消息含指标名/已验证值/偏差）；601066（站上 22.61 vs 现价 23.03 → empty_trigger）；「跌破近期低点 22.94」现价 23.03 → 无 anomaly；「单季净利降幅收敛至 18.35% 以下」「赔率修复至 1:1」→ 无 anomaly。risk_judge 接入测试：构造 stub 决策含问题触发价 → 返回 dict 含 decision_price_anomalies 且管线不中断（异常路径 mock call_llm_for_json）。

报告标注在 Task 3 渲染时一并处理（reeval_triggers 行渲染时查 decision_price_anomalies 同源文本）。

---

### Task 2: 非法仓位档位渲染归一（tasks 2.1–2.2）

**Files:**
- Modify: `src/finance_agent/nodes/report.py`（_format_trade_decision 的仓位行）
- Test: `tests/nodes/test_report_decision_render.py`（新建或并入既有报告渲染测试）

**行为契约：** 档位词表 `{light, moderate, heavy}` 大小写不敏感；`position_size` 为 None/空串/不在词表（如 "none"）→ 渲染「未提供」；合法档位含大小写变体按原值渲染；归一 MUST NOT 回写决策对象（渲染函数只读）。测试锚点：600515 形态（"none" → 未提供）；"Light" → 原值渲染；None → 未提供。

先读 `_format_trade_decision` 现状（仓位行渲染方式），保持其余行零改动。

---

### Task 3: buy/sell 终稿 reeval_triggers 必填化 + 报告渲染（tasks 3.1–3.2）

**Files:**
- Modify: `src/finance_agent/nodes/risk.py`（risk_judge 增 `final_reeval_check` 三路检查：在 final_inaction_check 逻辑后扩展——buy/sell 且清洗后 reeval_triggers 为空 → 打回一次（feedback 引用风险辩论共识线索：「可从风险辩论中保守/中性方已提出的触发条件结构化申报」），仍缺 → 放行 + note「已打回仍未申报再评估触发条件」；buy/sell 有 ≥1 条 → pass。注意与 final_inaction_check 的重试交互：沿用其「重试后复核前序结论」模式）
- Modify: `src/finance_agent/nodes/report.py`（_format_trade_decision：buy/sell 也渲染「再评估触发条件」行——非空逐条编号渲染，空/缺渲染「未申报」；渲染时挂 Task 1 的 decision_price_anomalies 同源标注「（价位待核实：<已验证值>）」）
- Test: `tests/nodes/test_risk_reeval_check.py`

**行为契约：** spec agent-node-contracts「非执行动作结构化理由契约」MODIFIED 的四个 buy/sell Scenario + report-decision-rendering「交易决策节渲染操作参数」MODIFIED 的 buy/sell 两 Scenario。清洗噪声形态（null/单字符串/混合列表）由 TradeDecision 既有清洗承担——先读 models.py 的 reeval_triggers 清洗确认形态（若清洗在 model validator 则直接测 model；缺失则本任务补）。601818 形态复现：sell + reeval_triggers=[] → 打回一次 → 仍空 → 放行 + final_reeval_check.note + 报告「未申报」。

---

### Task 4: FM 可见性 + 置信度语义（tasks 4.1–4.5）

**Files:**
- Modify: `src/finance_agent/nodes/fund_manager.py`（FM 上下文注入终稿完整性标注：final_price_check/final_inaction_check/final_reeval_check 的 note 非空时进上下文；上下文含 final_trade_decision 完整字段——先读现状确认是否已含）
- Modify: `src/finance_agent/nodes/report.py`（FM 节：note 非空时先渲染「审批对象结构不完整标注」再渲染 FM 意见；置信度漂移标注：FM approve 且 |FM confidence − 终稿 confidence| > 0.15 → 「置信度漂移：FM 0.8 / 终稿 0.55」+ FM reasoning 全文）
- Modify: `src/finance_agent/prompts/fund_manager.md`（confidence 语义=对本次裁决正确性的置信度、漂移说明义务、复述保真约束——指标名与结构化参数逐字引用、不得混同量纲）
- Modify: `src/finance_agent/prompts/risk_judge.md`（confidence 与 reasoning 一致纪律）
- Test: `tests/nodes/test_fm_visibility.py`

**行为契约：** spec agent-node-contracts「FM 审批对象完整性可见性」三 Scenario +「Fund Manager 操作性结论字段」MODIFIED 的漂移披露/复述可观测 Scenario。锚点：600515（FM 0.8 vs 0.55 → 漂移标注含两值）；≤0.15 无标注；方案完整时零增量（无空标注行）；reject/return 不产漂移标注。

完成 4.4 后执行 prompt 发布（凭据 source ../../.env），4.5 的 prompt-deploy-consistency 门禁由 deploy 成功输出佐证。

---

### Task 5: 收口

- [ ] `uv run ruff check` 全绿、`uv run mypy src/` 81 持平、`uv run pytest tests/ -q --ignore=tests/evals`（或等价定向全集）全绿
- [ ] metrics.md 时间线备注新 anomaly 信号（只观测不进处置）
- [ ] validation 报告落 `tests/validation/2026-09-30-update-decision-integrity-gates-validation.md`（逐 Scenario 对照 + 六个股票 ticket 形态复现状态）+ tasks.md 回填
- [ ] openspec validate update-decision-integrity-gates --strict 通过

## Self-Review 记录

- Spec 覆盖：price-level-tooling ADDED 1 requirement 4 Scenario → Task 1；report-decision-rendering MODIFIED 2 requirement → Task 2/3；agent-node-contracts ADDED 1 + MODIFIED 2 → Task 3/4。tasks.md 1–5 全映射。
- 决策层既有测试基线：risk.py 的 final_price_check/inaction 相关测试（tests/ 内 grep final_price_check）在 Task 3 改动后必须保持绿——重试交互按「重试后复核前序结论」既有模式。
- 无占位符；实现细节依赖各任务实施者对现状代码的侦察（打回/渲染既有形态已在任务中指明文件与函数）。
