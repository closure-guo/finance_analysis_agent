# extend-payout-self-check-coverage Implementation Plan

**Goal:** 赔率自检堵两个实证漏网（N倍 形态盲区、终稿价位缺失直通）+ 转述护栏防误改。

**Architecture:** 全部确定性修复：`validate.py::check_and_fix_stated_ratio` 扩正则 + 护栏；`risk.py` 出口加终稿价位完整性打回（一次重试，二次放行+标注）。零 LLM 判定。

**Tech Stack:** 纯 Python（re / pydantic model_copy），pytest 回归。

## Global Constraints

- 转述护栏词表：`("批评", "激进方", "保守方", "中性方", "对方", "辩论")`（实证枚举，design.md 记录）
- `N倍` 替换写法：`f"{derived_ratio:.2f}倍"`（保留原「倍」字，数字带两位小数）
- 容差不变：相对 10% 以内不修正
- telemetry：跳过计数键 `payout_ratio_conflict_skipped`（int，逐处累加），与 `payout_ratio_corrected`（bool）同节点返回
- 终稿价检：只校验 buy/sell 三价位完整性（None/≤0），不重跑关系/参考带；打回键 `final_price_check_feedback` + attempts 上限 1，放行标注 `final_price_check` note

---

### Task 1: check_and_fix_stated_ratio 扩形态 + 转述护栏

**Files:**
- Modify: `src/finance_agent/nodes/validate.py:67-100`
- Test: `tests/nodes/test_validate_payout.py`（或并入现有 validate 测试文件——查 `apply_payout_self_check` 现有测试位置后落同一文件）

**Interfaces:**
- Produces: `check_and_fix_stated_ratio(reasoning: str, derived_ratio: float | None) -> tuple[str, bool]`（签名不变）；`apply_payout_self_check` 返回值扩为 `tuple[str, bool, int]`（文本, 是否修正, 跳过计数）——**破坏调用方 trader.py/risk.py 各一处，同任务内更新**

- [ ] Step 1 失败测试：
  - `test_nbei_form_replaced`：reasoning「赔率约1.78倍纸面占优」派生 1.57 → 替换「1.57倍」+ corrected True（600030 实证）
  - `test_transcript_guard_skips_but_counts`：「激进方对赔率1.55:1不合格的批评被部分采纳」派生 2.23 → 原文不变 + skipped 1（601888 实证）
  - `test_guard_words_do_not_affect_plain_conflict`：无指涉词窗口照常替换（护栏不误伤）
  - `test_n1_regression`：既有 `N:1` 判例（1.7:1 vs 1.24）仍替换
- [ ] Step 2 跑测确认红
- [ ] Step 3 实现：正则 `r"(\d+(?:\.\d+)?)\s*[:：]\s*1"` 扩为或匹配 `r"(\d+(?:\.\d+)?)\s*倍"`；窗口内指涉词 → skipped += 1 不替换；`apply_payout_self_check` 透传 skipped
- [ ] Step 4 跑测确认绿 + 调用方（trader.py / risk.py）同步更新返回解包与 state 键
- [ ] Step 5 提交

### Task 2: risk_judge 终稿价位完整性打回

**Files:**
- Modify: `src/finance_agent/nodes/risk.py`（出口处，`TradeDecision.model_validate` 之后）
- Test: 同 Task 1 测试文件（或 `tests/nodes/test_risk.py` 现有文件）

**Interfaces:**
- Consumes: Task 1 的 `apply_payout_self_check` 新返回形态
- Produces: state 键 `final_price_check`（{result: pass|fail|retry_exhausted, note}）、`final_price_check_feedback`（str|None）

- [ ] Step 1 失败测试：
  - `test_final_decision_buy_missing_price_first_retry`：action=buy 价位 None → 打回重试一次（LLM 第二次调用 feedback 含缺失项）
  - `test_final_decision_retry_exhausted_passes_with_note`：重试仍缺 → 放行 + `final_price_check.result="pass"` note「已打回仍未申报」（避免下游死循环，同 Trader 价检语义）
  - `test_final_decision_complete_prices_no_extra_call`：价位齐全 → 单次调用直通
  - `test_watch_no_price_requirement`：watch → 直通（无价位要求）
- [ ] Step 2 红
- [ ] Step 3 实现：`_final_price_missing(decision) -> list[str]`；缺失且 attempts<1 → 把 feedback 拼进 context 重跑一次 `call_llm_for_json`；仍缺/齐全 → 放行 + note
- [ ] Step 4 绿 + trader/risk 既有测试零回归
- [ ] Step 5 提交
