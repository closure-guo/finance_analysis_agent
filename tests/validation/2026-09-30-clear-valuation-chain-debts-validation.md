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
2. **既有 bug 暴露：SSE 客户端断开误标会话 failed**（api.py:1175 except Exception 兜底把 curl --max-time 断开当管线失败，failure_reason=None；管线线程实际仍在跑）。非本 delta 引入（fetch 慢放大了断开落在生成窗口的概率）。**挂账**：建议 A 类修复（SSE 连接异常 SHALL NOT 覆写会话终态，终态由 pipeline_runner 全权负责）——属 session-streaming 域，未入本 delta 范围。
3. Task 5 派发代理被环境取消（无产出），controller 内联实施完成；Task 3 实施者的根因修复偏差（修 `_normalize_nan` 而非简报插行）经审查三项核实裁定成立。

## 结论

- [x] 全部通过，可 archive（前置条件：tasks.md 全勾 ✅、静态门禁 ✅、人工验证报告本件 ✅、openspec validate --strict ✅）
- [ ] 存在失败项，需修复后重新验证

**遗留（挂账，非阻断）**：SSE 断开误标 failed（见异常 2，建议 A 类或 session-streaming 小 delta）；同业批抓取共享 spot 表优化；GARP `_clean_num` numpy 标量 nit；报告估值「有值」分支 None 内插文案病（backlog）。
