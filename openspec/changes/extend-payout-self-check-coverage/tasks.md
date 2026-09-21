# Tasks: extend-payout-self-check-coverage

- [ ] `N倍` 形态自报冲突原位替换（600030 实证形态回归测试绿）
- [ ] 转述护栏：辩论指涉词窗口跳过替换 + `payout_ratio_conflict_skipped` 计数（601888 实证形态回归测试绿）
- [ ] `N:1` 既有语义零回归（601899/000333 原判例测试仍绿）
- [ ] risk_judge 终稿 buy/sell 价位缺失首次打回、二次放行 + `final_price_check` 标注（601888 实证形态回归测试绿）
- [ ] 终稿价位完整直通无额外调用
- [ ] 全套测试通过（`-m "not live"`）+ 验证报告落 `tests/validation/`
