# 人工验证报告: clear-valuation-chain-debts

**日期**: 2026-09-30
**验证人**: controller（ZCode agent；Task 5 由 controller 内联实施——派发代理被环境取消）
**关联 delta**: openspec/changes/clear-valuation-chain-debts/
**E2E 门禁**: 不适用（纯后端数据管道/渲染变更，非交互类）
**分支**: feat/fin-freshness-valuation（延续上一 delta 工作分支，基于其 archive commit 634813d6）

## 验证结果

验收方式：静态门禁（全绿）+ **真实数据离线驱动**（akshare 实抓拓荆/中微/北方华创，跑 compute→GARP→相对估值→披露节渲染）。原定 LLM 全管线实跑在东财全封日 fetch 阶段超 15 分钟未完成，且暴露一处**既有 bug**（见异常记录 2）——改用离线驱动完成本 delta 增量面的验收（上一 delta 已有 4 轮全管线基线，本 delta 增量不涉及 LLM 层）。

| Scenario / 任务 | 预期 | 实际结果（真实数据实测） | 通过 |
|---|---|---|---|
| D1 GARP ROE 缺失报缺失 | 「ROE 数据缺失（未参与比较）」+ ROE_missing | 单测 4 态 × 3 指标全绿；真实数据下 GARP failures=[「行业平均 PE 数据缺失（未参与比较）」（诚实桶），「负债率 >= 60%」（真实失败，年报口径 64.1%）] 分桶可辨 | ✅ |
| D1 负债率 NaN 不伪装通过 | NaN → 缺数桶 | test_debt_nan_treated_as_missing_not_pass（红阶段实证 NaN 曾静默通过） | ✅ |
| D2 同业抓取真实回退链 | DataFrame name/code/PE/PB | 实抓 688012/002371：两行成功，PB 10.36/11.26（回退链），PE 诚实 None（回退链无 PE） | ✅ |
| D2 相对估值复活 | peer_financials 有值即计算 | 相对估值 PB 口径：拓荆 15.09 vs 同业均值 10.81 → **overvalued**；PE 同业全缺 → N/A + caliber_note 跨口径提示（I1 修复联动） | ✅ |
| D2 NaN peer 不毒化均值 | NaN PE/PB 跳过 | 复审 ⚠️ 修复 43ce2cb8（np.float64(nan) 穿透实证红→绿） | ✅ |
| D3 出口 NaN 归一 | 全列无 NaN | 真实数据 quarterly gross_margin=[40.58, 41.69, 38.02, 34.42]（拓荆单季毛利率序列首次可见） | ✅ |
| D4 披露节编号化+暂缺 | 无 ### 标题、无「暂缺%」 | 真数据渲染：正文无标题（generate_report 编号注入）、无暂缺单位形态、无字面 None | ✅ |
| D5 健康度进度行 | 取 total | api.py 修正 + grep 全仓无残留旧取值；api 回归 22 passed | ✅ |
| D6 门禁扩展 fetch 产出 | fetch 键 ⊆ AnalysisState ⊆ 通道 | 实测差集为空（守卫补强，测试直接绿）；门禁用例常驻防回归 | ✅ |

## 静态门禁（收口时新鲜运行）

- ruff check → All checks passed；mypy src/ → 81 errors（基线持平）
- 定向回归（nodes/metrics/data/citation×3/vocab/cache/graph/prompt×2）→ **896 passed, 0 failed**

## 异常记录

1. **带 peer_codes 的 LLM 全管线 run 失败（fetch 超慢）**：东财全封日每标的回退链 ~90s+，fetch 阶段 15 分钟未完成（主标的+2 peer+kline+行业 PE 全在回退）。**非本 delta 引入**（回退链是既有设计；fetch_peer_data 复用之，Task 2 审查已备注成本可接受）。处置：验收改离线驱动（如上）。改进候选（挂账）：同业批抓取共享单次 spot 表。
2. **（定性已更正 2026-09-30）管线瞬态异常 + 终态观测洞**：journal 错误事件实证 4c038a41 的 failed 来自管线执行体自身异常（fetch 阶段「DataFrame truth value ambiguous」，瞬态网络形态，graph 层重放未能复现），**并非** SSE 断开误标——`_run_graph_streaming` 是管线本体，其 except 写 failed 是正确职责。真缺陷是观测洞：①update_session_status 未带 failure_reason（库中 None）②error 事件 traceback 字段存对象 repr 零信息。**已修**（api.py 终态补 reason + format_exc，契约测试 test_pipeline_exception_observability 2 用例）；瞬态根因待下次发生用新 traceback 定位（挂账）。fetch 线程池 future 在生成器死后继续跑造成「管线还活着」假象，扩大了排查成本——已知现象，无行动项。
3. Task 5 派发代理被环境取消（无产出），controller 内联实施完成；Task 3 实施者的根因修复偏差（修 `_normalize_nan` 而非简报插行）经审查三项核实裁定成立。

## 结论

- [x] 全部通过，可 archive（前置条件：tasks.md 全勾 ✅、静态门禁 ✅、人工验证报告本件 ✅、openspec validate --strict ✅）
- [ ] 存在失败项，需修复后重新验证

**遗留（挂账，非阻断；2026-09-30 清偿状态）**：~~同业批抓取共享 spot 表~~（已修 626a56c8）、~~GARP `_clean_num` numpy 标量~~（已修 v!=v）、~~缓存读出口 30 天 NaN 窗口~~（已修 check_cache 读出口归一）、~~SSE 误标~~（定性更正为管线瞬态异常，观测洞已修）；仍开：瞬态 DataFrame 异常根因（待复现用新 traceback 定位）、报告估值「有值」分支 None 内插文案病（backlog）、fetch_peer_data 无整批 deadline（共享 spot 后总时长可控，暂不做）。

## 终审记录（2026-09-30）

独立终审裁决 Needs fixes（1 Critical）→ 修复 commit 1689e435 → 复核 **Approved（可 archive）**。

- **C1（终审发现，端到端实证）**：fetch_peer_data 行级 NaN 归一在 DataFrame 构造边界失效——混合双行（一 peer PE=None + 一 peer PE 有值）时 None 被强转回 float64 NaN，毒化同业均值（peer_avg=nan）且三向比较恒 False 伪装成 "fair"。修复：出口复用 `_normalize_nan` 根因归一（与 D3 同法）+ relative.py 纵深守卫 + 混合双行用例。
- **I1**：D6 门禁盲区——stub 缺真实路径 4 键（kline/benchmark_kline/industry_pe/quarterly_income）且 docstring 声明失实。修复：stub 键集与真实路径同构（19 键）+ docstring 修正；连带修复 stub 空 kline 引起的两个全图测试失败（改有效 80 期 kline）。
- **I2**：ADDED 四场景测试映射缺口补齐（_fetch_peers 节点级守卫直测 ×2）。
- 终审独立复现确认：修复前同输入 `peer_avg: nan, conclusion: 'fair'` → 修复后 `peer_avg: 60.0` 结论正确。挂账定性复核：SSE 断开误标 failed 确认为存量（blame 2026-07-09，早于本 delta）。
