# 人工验证报告: update-decision-integrity-gates

**日期**: 2026-09-30
**验证人**: controller（ZCode agent；本 delta 系接手另一会话 2026-09-28 的休眠立项，用户指令「全修」授权实施）
**关联 delta**: openspec/changes/update-decision-integrity-gates/
**E2E 门禁**: 不适用（纯后端决策层校验/渲染变更，非交互类）
**分支**: feat/fin-freshness-valuation（Task 1：cc61ae6a；Task 2：35295396；Task 3：f4f3b277；Task 4：5bd70c20+dbe7191e）

## 验证结果

验收方式：TDD 单测逐 Scenario 落实（每个任务独立 task-reviewer 审查通过）+ 定向回归全绿。六个股票 ticket 形态以单测复现（对照真实 cohort 报告形态构造输入）。

| Scenario / ticket | 来源 spec | 实现与测试 | 通过 |
|---|---|---|---|
| 600845 触发价幻觉（18.8 vs MA60 18.066） | price-level-tooling 偏差形态 | `test_decision_price_check.py` 偏差 4.06% anomaly 含指标名/已验证值/幅度；管线放行 | ✅ |
| 601066 空洞触发（站上 22.61 vs 现价 23.03） | 同上空洞形态 | empty_trigger anomaly（上破词+价位≤现价）；放行 | ✅ |
| 600015 降幅阈值不误报（18.35% / 赔率 1:1） | 同上量纲归类 | 非价格量纲排除，8+ 反例族测试 | ✅ |
| 600515 非法档位 "none" 透传 | report-decision-rendering 档位归一 | 渲染「未提供」，原值保留落库（不回写），6 形态参数化 | ✅ |
| 601818 sell 无触发条件仍获批 | agent-node-contracts reeval 必填化 | 打回一次 → 仍空放行 + final_reeval_check note + 报告「未申报」行；≥1 条直通 | ✅ |
| 600515 置信度 0.8 vs 0.55 无解释漂移 | 同上 FM 置信度语义 | 报告操作定性旁「置信度漂移：FM 0.8 / 终稿 0.55」；≤0.15/reject/None 无标注 | ✅ |
| 002916/600015 FM 复述失真 | 同上复述保真 | prompt 保真约束（逐字引用/量纲不混同）+ 上下文含上游原文 + judge 变量含 reasoning 全文（可观测，代码不硬判语义） | ✅ |
| 601818 FM「执行安排完备」与事实矛盾 | FM 完整性可见性 | 三 check note 非空 → FM 上下文注入 + 报告先渲染结构不完整标注再渲染 FM 意见；「打回后已申报」复核类标注不进报告（终审裁定：渲染=自称不完整，错话） | ✅ |
| 噪声清洗不炸管线 | 非执行动作契约噪声 Scenario | models 既有 validator 锁定测试（null/单字符串/混合列表） | ✅ |

**关键实现决策（task-reviewer 裁定成立）**：「打回后已申报」等复核性 note 不属于「结构不完整标注」——渲染它们等于报告自称方案不完整（错话，与终审 I-1「打回后已申报是错话」先例同族）；FM 上下文保留全量 note（信息不隐藏）。

## 静态门禁（收口时新鲜运行）

- ruff check → All checks passed；mypy src/ → 81 errors（基线持平）
- 全量回归 `uv run pytest tests/ --ignore=tests/evals` → 见收口 commit 记录（evals 排除因含 @live 烧 LLM 用例，属 CI nightly 域）
- prompt 发布：deploy_prompts 导入 2（fund_manager/risk_judge）、跳过 12、失败 0

## 异常记录

1. **test_derived_series_channel / test_pipeline_stub 三例顺序耦合 flaky**（既有）：依赖共享 cache.db 预热状态（冷缓存 MISS → stub fetch 覆盖注入 state）。已修：testing_env 与 derived_series_channel 测试加缓存隔离（monkeypatch get_shared_cache → :memory:，incident 031 同族卫生）。stash 隔离验证非本 delta 引入。
2. **stub 键集漂移**（既有）：stub 恒置 peer_financials=None vs 真实键缺席——结构化相等断言（TestStubRealKeysetParity）抓出后删 stub 占位对齐。

## 结论

- [x] 全部通过，可 archive（tasks.md 全勾 ✅、静态门禁 ✅、本报告 ✅、openspec validate --strict ✅）
- [ ] 存在失败项，需修复后重新验证

**挂账（非阻断）**：价位校验器精度 nit ×5（方向词就近匹配/「已」字豁免窗/「120日均线」别名前缀/千分位逗号/参考带合取语义——均观测旁路噪声/漏报级）；final_reeval_check.result 恒 pass 与同族一致（eval 若需 result 区分再议）；FM marker 中文字串跨文件耦合（更稳做法=结构化 incomplete 字段）；复核性标注是否进报告（spec 字面可两读，改须走 delta）。
