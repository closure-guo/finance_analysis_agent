# 人工验证报告: update-financial-freshness-and-valuation

**日期**: 2026-09-29
**验证人**: controller（ZCode agent，用户授权「开始」实施）
**关联 delta**: openspec/changes/update-financial-freshness-and-valuation/
**E2E 门禁**: 不适用（纯后端数据管道变更，非交互类，见 project-workflow.md §2 判别）
**分支**: feat/fin-freshness-valuation（worktree .worktrees/fin-freshness-valuation）

## 验证结果

验收方式：worktree 后端独立运行（端口 8010、SESSIONS_DB_PATH/REPORTS_DIR 隔离、缓存清空冷启动），对拓荆科技(688072) 跑真实 LLM 全管线，对终版报告逐条核对 delta spec 场景。共 4 轮运行（20:54 / 21:08 / 21:24 / 21:32），前两轮暴露两处存量数据 bug（见异常记录），修复后终版 5/5 通过。

**终版报告**: `reports_worktree/拓荆科技_688072_20260929_213219_report.md`（session 6be5387e-37d）

| Scenario | 来源 spec | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 最新报告期快照进入上下文并出现在报告 | analyst-data-sources「分析师消费最新报告期快照」 | 报告呈现中报毛利率/负债率/存货/合同负债 | 披露节：「2026-06-30（中报，利润表累计口径）— 毛利率 41.0%、资产负债率 47.85%、存货 88.33 亿、合同负债 51.31 亿，营收同比 49.08%、归母净利同比 1328.72%」；LLM 章节（L84）亦引用 | ✅ |
| 年报下滑与中报回升并陈（冲突显式说明） | 同上 Scenario「中报回升与年报下滑并陈」 | 不得只引其一 | LLM 关键发现：「年报毛利率连续三年下滑（2022年49.27%→2025年34.95%），但最新2026中报毛利率回升至41.0%，趋势已被打破转好」「负债率64.11%偏高——但最新2026中报已降至47.85%」 | ✅ |
| PE 缺失时 TTM 推导 + 口径可辨 | valuation-signal-integrity「PE 缺失时的 TTM 确定性推导」 | derived_ttm 口径出现在报告 | 本次运行东财行情被封走百度回退（quote 无 PE，backend 日志 21:32 实录）→ 披露节「市值 1918.64 亿、PE 88.17（TTM 推导口径）、PB 15.09」；LLM 辩论/决策章节全部以「PE_ttm 88.17」引用 | ✅ |
| GARP 缺数据诚实文案 | valuation-signal-integrity「估值缺数据的诚实文案」 | 无「PE >= 行业平均」伪文案 | 报告全文无该字串；GARP 输入（Langfuse run2 trace 实证）failures=[「行业平均 PE 数据缺失（未参与比较）」，…]，details 含 PE=88.17 与 PE_caliber=derived_ttm | ✅ |
| 健康度行业口径披露 | industry-threshold-coverage「健康度评分行业口径披露」 | 渲染层可见评分口径 | 披露节：「财务健康度：48.8 分（warning），评分采用 行业口径：半导体设备（行业阈值覆盖：存货周转率、应付账款周转率、速动比率）」；健康度 40→48.8（存货周转/速动红灯降黄灯） | ✅ |
| 季度趋势含单季毛利率 | analyst-data-sources「季度利润表字段扩展」 | quarterly_trend 携带毛利率序列 | 单测（test_compute_quarterly_trend 4 用例）+ run1 报告「2026Q2 单季毛利率」引用；revenue_yoy 于 fetch 层宽窗口计算（审查升级修复） | ✅ |
| citation 新键解析 | delta tasks.md citation 项 | 三类新键 claim PASS | tests/test_citation_new_keys.py 3/3；附带修复两处解析病（canonical_metric 剥单位后缀、重算路径 [N] 展开） | ✅ |

## 异常记录（发现→修复→回归，全部已提交）

1. **run1→run2（21:08）④失效**：industry_override 未命中。根因一：`_fetch_industry_cninfo` 取变更史 `iloc[0]` = 最旧条目（拓荆拿到 2021 年「其它专用机械」）——commit cce921b。根因二（run3 复现）：同日 2022-04-20 巨潮「集成电路」与中证「半导体设备」并存，不稳定排序随机取前者——commit c0f7829（申万>中证>巨潮>证监会 tie-break + 稳定排序 + 日期列可选）。
2. **run2→run3（21:24）③⑤波动**：数据管线三轮 100% 稳定（Langfuse 输入实证估值/快照全在），但报告 markdown 引用随 LLM 方差缺失。根因：健康度口径/快照/估值无程序化渲染面，spec「报告渲染层 SHALL」被降级为 LLM 自觉——commit 61d52aeb 前置（`_format_freshness_section` 确定性披露节，4 单测）。
3. **Task 7 测试暴露存量死链**：`AKShareClient.fetch_peer_data` 从未实现（hasattr=False），生产 `_fetch_peers` 必抛错被吞，`peer_financials` 恒 None，**相对估值自 P1 数据层起从未在生产计算过**。不在本 delta 范围（个股估值维度已由 PE_ttm 修复覆盖），挂 incident 033 后续清单待 owner 裁决。

## 静态门禁（收口时新鲜运行）

- `uv run ruff check` → All checks passed
- `uv run mypy src/` → 81 errors（与 main 基线持平，零新增）
- 定向回归（nodes/metrics/data/citation/vocab/prompt/graph/cache）→ 878 passed, 0 failed
- prompt 发布：`deploy_prompts.py` 导入 1（fundamental_analyst）、跳过 13、失败 0（Langfuse production）

## 结论

- [x] 全部通过，可 archive（前置条件：tasks.md 全勾 ✅、静态门禁 ✅、人工验证报告本件 ✅、openspec validate --strict ✅）
- [ ] 存在失败项，需修复后重新验证

**遗留（不阻断 archive，待 owner 裁决）**：fetch_peer_data 死链（相对估值同业段）；revenue_yoy round 口径与 fetch 层 NaN 非 None 语义（与既有环比/同比列同病）；missing_reasons 重复文案；decision-integrity-gates 在途 delta 的推进归属。
