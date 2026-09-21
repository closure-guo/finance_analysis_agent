# Proposal: extend-payout-self-check-coverage

## Why

赔率自述矛盾证据已 strengthened 至四例（601899 终稿 / 000333 初稿 / 600030 终稿 / 601888 终稿），横跨 Trader 与风控层、两个批次。§19.12 跑批归因实证发现现有自检（`apply_payout_self_check`，已挂 trader 与 risk_judge 出口）存在两个漏网：

1. **表述形态盲区**：替换正则只匹配 `N:1` 冒号形态（spec 原文亦只写 `N:1` 型），而 600030 终稿实际形态是「赔率约1.78倍纸面占优」——risk_judge 改了止损（25.42→25.3，派生赔率 1.77→1.57）但文本残留旧价位算出的 1.78，自检未触发（`payout_ratio_corrected: False` 实测）。
2. **价位缺失直通**：601888 终稿 action=buy 但 entry/stop/target 全 None（价位埋在 reasoning 文本中）→ 派生赔率 None → 自检按「缺失跳过」豁免；`final_trade_decision` 的 buy/sell 无价位校验（价位必填打回只挂 `trader_plan`），管线放行。

## What Changes

- 赔率自检替换窗口正则扩展：`N:1` 之外识别 `N倍` / `N 倍` 形态（MODIFIED `derived-risk-metrics`「LLM 自算数值不作为下游真值」）
- **转述护栏**：替换窗口内含辩论指涉词（批评/激进方/保守方/中性方/对方/辩论）时跳过替换、仅计数上报（`payout_ratio_conflict_skipped`）——防「错改正述」（FM/risk 转述辩论对方的数字时，替换可能反转批评语义）
- `final_trade_decision`（risk_judge 写入方）buy/sell 价位完整性校验：任一缺失首次打回重试一次，仍缺放行 + 如实标注（同 `trader_plan` 价位必填语义，MODIFIED `price-level-tooling`「交易价位 sanity 校验」）

## Capabilities

- **Modified Capabilities**: `derived-risk-metrics`（自检形态与护栏）、`price-level-tooling`（价位校验覆盖面）

## Impact

- `src/finance_agent/nodes/validate.py`（`check_and_fix_stated_ratio` 正则 + 护栏）、`src/finance_agent/nodes/risk.py`（终稿价检打回回路）
- FM（`fund_manager.py`）**不挂**自检——裁决见 design.md：FM reasoning 为审批转述文本，修复路径已由上述两项覆盖源头
- 验证证据：`reports/ablation/p2/materials-20260920`（600030/601888 实测）+ `docs/evals/metrics.md` §19.12/§19.13
