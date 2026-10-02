# Proposal: update-decision-price-gate-admission

## Why

incident 034 遗留的 owner 终裁（已批）：门禁阻断的准入按「恶化判据」分层。实证背景——688072 第二跑中 LLM 收到打回反馈后精确响应（改写触发条件、显式声明「而非当前640价位下直接满足」），但因校验器句法规则无法识别复合条件语义而坚持原价位，残留 anomaly 与首次**完全同源且未增多**，门禁仍阻断交付。这类「LLM 有理由申辩 + 未恶化」的形态与「重试后仍输出新错误/错误增多」性质不同：前者多为校验器语义盲区（应放行+标注+人工终裁），后者才是真错误顽固形态（应阻断）。incident 026 纪律（自动化处置只挂真错误桶）在此的落地：未知误报形态的代价不应由用户承担（拿不到报告），而应由观测通道承担（trace 标注 + issue 化终裁）。

## What Changes

- **门禁准入分层**：打回重试后残留 anomaly 非空时，按与首次 anomaly 集合的比较分情形——
  - **未恶化**（残留条数 ≤ 首次 且 残留 source_text 均在首次集合内）→ 降级**放行**：决策进 FM 审批，gate note 如实标注「打回后残留 N 条未清零（未恶化，放行待人工终裁）」，残留 anomaly 照落 state/trace；
  - **恶化**（残留条数 > 首次，或出现首次集合外的新 source_text）→ 维持**阻断**（gate fail）；
- 首次校验无 anomaly 直通、打回后清零放行的既有行为不变；
- 恢复 anomaly 观测的 issue 化通道：放行形态的 gate note 进 FM 上下文（既有 FINAL_CHECK_LABELS 机制）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `price-level-tooling`: 「打回后仍异常阻断交付」requirement 的处置分层（未恶化放行+标注 / 恶化阻断）

## Impact

- `src/finance_agent/nodes/risk.py`：gate 判定增加残留 vs 首次比较逻辑（纯函数级，复用 source_text 集合）
- `src/finance_agent/state.py`：`decision_price_gate` 注释更新（note 新增第三形态）
- `src/finance_agent/nodes/fund_manager.py`：无需改动（FINAL_CHECK_LABELS 已挂 gate，note 自动进上下文）
- 测试：`tests/nodes/test_risk.py` 新增分层用例；`tests/test_api_blocked_terminal.py` 既有 fail 用例改用恶化形态夹具（残留新增 source）
- 非交互类变更 → 不适用 E2E 门禁
