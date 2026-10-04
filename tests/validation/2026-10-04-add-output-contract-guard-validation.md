# 人工验证报告: add-output-contract-guard

**日期**: 2026-10-04
**验证人**: ZCode agent（程序化验证 + 逐项核对；报告内容主观质量待 owner 核读）
**关联 delta**: openspec/changes/add-output-contract-guard/
**E2E 门禁**: 不适用（纯后端逻辑变更，非交互类，§3.5 不触发）
**部署验证**: PR #221 squash 合并（main `ae8697a4`）→ `docker compose up -d --build` 重建（20:00 前，backend healthy）

## 验证环境

- 生产会话 `f2db3c94-406`：深度分析拓荆科技（688072），2026-10-04 20:00 发起，**149 秒 completed**，报告 8358 字，md/pdf/pptx/docx 四件套落盘
- 选择拓荆的理由：incident 036 泄露实测发生在该标的（同日 3 次摘要调用泄露 2 次），是守卫的目标回归场景（处置第 3 条「换模型固定回归集」）

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 研究聚焦段无思考独白泄露 | 否 | 交付段不含 5 类泄露模式（the user wants / Draft: / Key points / Important constraint / Let me 系行首） | 对交付报告全文扫描：0 命中；守卫本体 `validate_deliverable_text` 对研究聚焦段实跑：`GuardVerdict(ok=True, hits=[])` | ✅ |
| 无截断交付 | 否 | 非句中悬空收尾、finish_reason≠length 进交付 | 段落以完整句收尾；guard ok（truncated 两规则均未命中） | ✅ |
| 数字可溯源（036 伴生缺陷） | 否 | 正文数字与数据快照一致，无虚构 | 合同负债 51.31 亿与 2026-06-30 快照一致；036 实测虚构值 48.52 未复现 | ✅ |
| 置信度可溯源、漂移在阈内 | 否 | FM 与终稿偏差 ≤ 0.15 | RM 0.55 → FM 0.58，偏差 0.03；FM 段明示「置信度与终稿一致，无漂移」 | ✅ |
| guard 判定进 trace（可观测） | 否 | Langfuse report span metadata 含 `guard` | 生产 span（12:02:27Z）`guard: {"ok": true, "reason": null, "hits": []}`；同日本地测试批 8 条 report trace 同样携带 | ✅ |
| raw_reasoning 交付回退已移除 | 否 | content 为空不得回退 reasoning 当交付文本 | `report.py:345` 仅 `(text or "").strip()`；tests/nodes/test_report_focus_guard.py 空正文场景覆盖（worktree 344 passed） | ✅ |

## 异常记录

无失败项。

附注（非本次变更范围）：
1. 本地全量 pytest（worktree，合并前）3 failed 均为既有问题、main 基线同现——2 个 `@live` marker 测试（PR 门禁按设计排除）+ 1 个受其全局状态污染的 prompt contract 测试；与守卫无关
2. CI 全绿：lint-and-test 6m27s（pytest 全量 + claim benchmark + golden gates）+ e2e stub 11m56s

## 结论

- [x] 全部通过，可 archive（待 owner 核读研究聚焦段主观质量后执行 sync + archive）
