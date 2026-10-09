# 人工验证报告: add-peer-comparison

**日期**: 2026-10-09
**验证人**: ZCode agent（用户委托全链收尾）
**关联 delta**: openspec/changes/archive/2026-10-09-add-peer-comparison/
**E2E 门禁**: 不适用（非交互类变更，无前端 UI/SSE/会话/状态流转变改）
**关联 PR**: #275（特性）/ #280（实跑暴露的桥接 bug 修复）/ #281（R4 确定性渲染收口）

## 验证结果

| Scenario | 实跑验证方式 | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| R1 对比请求识别 | 实跑 ×4（`POST /api/analyze` query=「对比 A 和 B，分析一下」） | 单次 `run_deep_analysis`，主标的+peer_codes | 4/4 次均为单次调用（600519/000858 与 601318/601398 两组），无二次完整管线；search_stock 解析（run2/run4 显式代码输入时直接进工具） | ✅ |
| R2 对标股参数传递 | 同上 + 单测 | peer_codes 生效、显式优先闭包、无效剔除 | LLM 实际传参为**字符串**形态（schema 内省局限，#277 挂账），容错分支两次实跑生效，管线正确收到 `["000858"]`/`["601398"]` | ✅ |
| R3 同业材料注入 | Langfuse trace 取证（trace a6bf31ee…，session 8b12b325） | fundamental_analyst 输入含对照材料 | 输入（42,874 chars）含完整对照表（主标的首行，数字与注入材料逐字一致）与 TTM 跨口径注 | ✅ |
| R4 报告同业对比段（完整数据） | 实跑 session e74b597e（601318+601398） | 报告含同业对比段（对照+口径+相对估值结论） | 报告章节 `## 三、同业对比`：对照表（部分字段「—」如实标记）+ 口径标注 + TTM 跨口径注 + 「相对估值（PB）：0.95 vs 0.74 → 相对同业偏高」；数值与实源验证逐字一致 | ✅ |
| R4 peer 缺失如实声明 | 实跑 session f868d34c（600519 缓存命中→同业未执行） | 报告渲染缺失声明，无编造对比结论 | 报告章节渲染「同业数据不可用（抓取失败或未执行），无法提供同业对比；不作对比结论。」 | ✅ |
| fetch 实源验证 | worktree 直连真实源（AKShareClient.fetch_peer_data） | 扩展字段可得、降级符合 spec | 9 列契约逐字成立；五粮液全字段（PB 2.31/总市值 2738.86 亿/营收同比 20.87/净利同比 89.3/毛利率 80.29/报告期 2026-06-30）；平安/工行按字段级降级（银行毛利率缺失如实「—」）；3 标的 4.8s 无限流；PE 列缺失与既有腾讯主源取舍一致（#276 挂账） | ✅ |
| 无 peer 请求回归 | 单测（compute/analysts/report 全套）+ 日常批次（16:00/18:00 五任务 ok） | 无 peer 时行为与现状一致 | compute 不写 peer_comparison 键、分析师无注入段、报告无同业章节（测试钉死）；当日批次全 ok | ✅ |
| prompts 发布一致性 | `deploy_prompts.py`（production） | production == 本地 | deep_mode、fundamental_analyst 导入成功，其余 12 个「与 Langfuse production 内容一致」SKIP | ✅ |

## 实跑过程中发现并已修复的问题

1. **`api.py:426` 存量桥接 bug（PR #280）**：首次实跑（session 62f15098，failed）暴露 `_node_summary` 对 `peer_financials`（DataFrame）做真值判断 → `ValueError: The truth value of a DataFrame is ambiguous`。休眠链路激活后首次携带真数据即崩。一行修复 + 回归测试。
2. **R4 渲染缺口（PR #281）**：二跑实证对照材料注入与分析师产出全部成功，但报告组装 `_format_analyst_report` 只渲染 summary+key_findings（markdown 正文存量丢弃设计）→ R4 改为确定性渲染：`generate_report` 追加「同业对比」章节直出 `state.peer_comparison` + compact 相对估值结论。

## 备注（不阻塞，已挂账）

- #276：腾讯主源下同业 PE 系统性缺失（对照表 PE 列常态「—」，主标的 PE_ttm 回落附跨口径注）
- #277：harness `build_schema_from_function` 泛型/Optional 注解 fallback "string"（本次实跑二次实证 LLM 传串行为）
- #278：剔除告知依赖 prompt 纪律 + deep_mode 规则 7 文案张力——本次 4 次实跑未观察到误读
- 当日 cohort_batch（18:00）summary 有 3 failure + 7 个 budget_unknown 跳过——与本 delta 无关，待按 incident 026 纪律分桶归因
- 教训：休眠路径激活缺少真实验证覆盖（api.py:426 潜伏至首次真实携带 peer 数据才暴露）——后续激活休眠链路的 delta 建议把「真数据实跑」列为实施期任务而非合并后验证

## 结论

- [x] 全部通过，可 archive
