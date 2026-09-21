# 人工验证报告: extend-payout-self-check-coverage

**日期**: 2026-09-21
**验证人**: AI（owner 立项授权，2026-09-21 对话「立项」）
**关联 delta**: openspec/changes/extend-payout-self-check-coverage/
**E2E 门禁**: 不适用（纯后端节点行为，非交互类变更）

## 验证结果

| Scenario（spec） | 单测覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| N倍 形态自报冲突原位替换 | 是（test_nbei_form_mismatched_ratio_is_corrected） | 「赔率约1.78倍」→ 派生值替换，其余文字不动 | 绿；真实材料 600030 复算实证 corrected=True、1.78 残留消除 | ✅ |
| N倍 容差内不修正 | 是（test_nbei_form_within_tolerance_untouched） | 1.6 vs 1.57（2% 差）原样 | 绿 | ✅ |
| 转述护栏：批评语境跳过+计数 | 是（test_transcript_guard_skips_but_counts + test_guard_word_variants_all_skip） | 601888「1.55:1不合格的批评」原文保留、skipped=1 | 绿；真实材料 601888 复算实证 skipped=1 | ✅ |
| 主语词在数字后非转述（护栏不误伤） | 是（test_subject_word_after_ratio_is_not_transcript） | 600030「1.78倍纸面占优。激进方建议…」照常替换 | 绿（600030 真实文本即此形态） | ✅ |
| 无指涉冲突照常替换（两种形态） | 是（test_plain_conflict_unaffected_by_guard） | 1.55:1→2.23:1、1.5倍→2.23倍 | 绿 | ✅ |
| N:1 既有语义零回归 | 是（TestPayoutRatioSelfCheck 原判例 5 条） | 601899/000333 判例仍替换 | 绿（解包适配三元组后语义断言原样） | ✅ |
| 终稿 buy 价位缺失首次打回 | 是（test_buy_missing_price_first_retry_fills） | 第二次调用 context 含打回反馈、补齐后 note「打回后已申报」 | 绿 | ✅ |
| 终稿打回后仍缺放行+标注 | 是（test_retry_exhausted_passes_with_note） | 放行不虚构价位、note 列明缺失项 | 绿 | ✅ |
| 终稿价位完整直通零额外调用 | 是（test_complete_prices_no_extra_call） | 单次调用 | 绿 | ✅ |
| watch 无价位要求 | 是（test_watch_no_price_requirement + helper 测试） | 直通 | 绿 | ✅ |
| state 键图通道声明 | 是（state.py 补 payout_ratio_conflict_skipped / final_price_check；test_graph_5layer 13 绿） | 不被图静默丢弃 | 绿 | ✅ |

## 端到端实证（真实批材料复算，reports/ablation/p2/materials-20260920）

- **600030**：终稿派生 1.57（risk_judge 改止损 25.42→25.3）→ reasoning「赔率约1.78倍纸面占优」→ 替换为「1.57倍」、`corrected=True`、`skipped=0`
- **601888**：以 trader 价位派生 2.23 校终稿 reasoning → 转述「1.55:1不合格的批评」原样保留、`skipped=1`；该标的价位缺失（entry/stop/target None）由终稿价检打回层在管线内拦截（单测覆盖）

## 全套验证

- `uv run pytest -q -m "not live"`：**3046 passed / 2 skipped / 12 deselected**，EXIT=0（12:11，Langfuse 在线生产口径）
- `uv run ruff check` + `ruff format`：通过
- mypy：改动文件 0 新增错误（`state.py` 报 2 个预先存在的重复键 price_levels/derived_series——main 基线噪声，非本 delta 引入，如实记录不动）

## 设计裁决记录（design.md 摘要）

- **FM（fund_manager）出口不挂自检**：FM reasoning 为审批转述文本，原位替换错改风险高于收益；两个实证漏网（形态盲区、价位缺失）均在 risk_judge 出口可修。立项时最初设想「FM 补挂」经根因分析后修正为当前三件套。
- **护栏词表收敛为批评语境词 + 12 字符近距离**：首版六词全窗口设计在 TDD 中被 600030 真实形态证伪（主语词在数字后是新句主语），按实证修正。

## 结论

[x] 全部通过，可 archive
