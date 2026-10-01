# 人工验证报告: update-quote-primary-source

**日期**: 2026-10-01
**验证人**: controller（ZCode agent，SDD T6）
**关联 delta**: openspec/changes/update-quote-primary-source/
**E2E 门禁**: 不适用（纯后端数据管道变更，非交互类，见 project-workflow.md §2 判别）
**分支**: feat/quote-tencent-primary（worktree .worktrees/quote-tencent-primary，base 2215ca4）
**运行环境**: 隔离冷启动——worktree 后端 8011 端口，独立 SESSIONS_DB_PATH/REPORTS_DIR/cache.db，真实 LLM；东货行情域对本机 IP 仍处封禁状态（本次验证的天然环境）
**会话**: 见 .verify-quote-src/sessions.db（session a8af3519 系列之外的新会话）｜**Langfuse trace**: `deep_analysis:拓荆科技` 53e82db2bbed8347c1b6cf5625dd9f6d（2026-10-01 21:28）
**报告**: `.verify-quote-src/reports/拓荆科技_688072_20261001_213135_report.md`（docx/pptx 同步导出）
**管线终态**: completed，159 秒

## 验证结果

对拓荆科技(688072) 跑真实 LLM 全管线，与 2026-10-01 incident 033 复跑基线（百度回退路径，`tests/validation/2026-10-01-incident033-postmerge-spotcheck.md`）逐项对照：

| # | 检查项 | 预期 | 实际结果 | 通过 |
|---|---|---|---|---|
| 1 | 腾讯主源命中 | 后端日志无「东财行情不可用」；quote 来自腾讯 | 日志仅有「东财**个股信息**不可用，降级 cninfo」（行业域，本 delta 范围外、封禁环境预期降级）；**零**「东财行情不可用」、零「腾讯行情直查失败」 | ✅ |
| 2 | 主源字段口径 | 披露节 PB=腾讯口径（14.55），区别于基线百度口径（14.71） | 披露节「估值快照：市值 1869.91 亿、PE 85.93（TTM 推导口径）、**PB 14.55**」——14.55 即腾讯串 field 46 金样本值，主源命中实锤 | ✅ |
| 3 | market_cap 量级 | 1869.91 亿（腾讯 field 45 亿×1e8 归一到元→compute 元→亿） | 1869.91 亿，与基线一致、量级正确 | ✅ |
| 4 | PE 契约 | 腾讯 PE（TTM 口径）不消费；quote 无 PE → compute derived_ttm | 披露节「PE 85.93（TTM 推导口径）」；Langfuse state `PE_missing: true, PE_caliber: "derived_ttm"`；LLM 全文以「PE_ttm 85.93」引用 | ✅ |
| 5 | GARP 诚实分桶 | failures 含「行业平均 PE 数据缺失（未参与比较）」，无伪文案 | Langfuse `failures: ["行业平均 PE 数据缺失（未参与比较）", "负债率 >= 60%"]` 与基线同构；报告全文无「PE >= 行业平均」（grep 0） | ✅ |
| 6 | 快照/健康度/季度趋势 | 与基线同构 | 中报快照（41.0%/47.85%/88.33 亿/51.31 亿/49.08%/1328.72%）、健康度 48.8 warning 半导体设备口径、单季毛利率序列引用均一致 | ✅ |
| 7 | 决策完整性 | 仓位「未提供」、FM 漂移披露、reeval_triggers 在场 | watch/55%/「仓位: 未提供」；FM 0.6「偏差 0.05，在阈值内」；触发条件三条在场 | ✅ |
| 8 | citation 分桶 | failed/unchecked 属「无法自动校验」覆盖缺口桶且数值正确 | 65 verified / 3 failed / 2 unchecked，failed 全部为推断类声明桶；49.08%/1328.72%/44.56% 与快照/quarterly_trend 数值一致（44.56%=2026Q2 单季同比，正确） | ✅ |
| 9 | 无东财 push2 调用 | 主源生效则封禁环境不应出现行情域请求 | 后端日志零行情域东财记录（若主源未生效必然出现「东财行情不可用」告警） | ✅ |

## 结论

- [x] 全部通过——腾讯主源在封禁环境实跑命中，口径契约（market_cap 元/亿换算、PE derived_ttm、PB 不融合）零漂移，下游（GARP/健康度/快照/决策完整性/引用）行为与基线等价
- [ ] 存在失败项

## 异常记录

1. citation 3 failed/2 unchecked 同「无法自动校验（LLM 推断类声明）」桶（与基线 run 同族），数值逐条人工核对正确——校验器覆盖缺口，非本变更引入，已在 incident 033 复跑记录中定性。
2. 原 C1 保留意见承接动作：`tests/validation/2026-09-29-update-financial-freshness-and-valuation-validation.md` C1 段已补 back-pointer（「已重新定性，见 docs/incidents/033」），随本分支入库。
