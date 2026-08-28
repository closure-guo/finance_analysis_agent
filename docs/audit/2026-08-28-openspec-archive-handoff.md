# OpenSpec Delta 归档大扫除 — 交接文档

**日期**: 2026-08-28
**分支**: `audit/openspec-archive-sweep` → 已推入 `main`
**用途**: 交接未完成的 OpenSpec delta 清理工作，供后续继续。

---

## 1. 已完成（本分支 4 个提交）

| Commit | 内容 |
|---|---|
| `542a009` | 归档 14 个已完成 delta + 主规范 sync 11→22 + 6 个变更 tasks 回填 + 审计报告（101 文件） |
| `2d5fcc9` | add-context-length-config 补实现（TDD，11 文件） |
| `0bd6684` | 再归档 add-llm-provider-gateway、truncation-resume-generation + data-ordering 2.4 核实 |
| `01f4ecb` | 审计报告更新至最终状态 |

**成果**：
- 归档 **16 个** delta（`openspec/changes/archive/2026-08-28-*`），删除 1 个归档重复残留（improve-decision-grounding）
- 主规范库 **11 → 22** capability（新建 llm-* 11 个 + report-export；智能合并 evaluation / trace-observability / frontend / pipeline-events / session-persistence）
- tasks 回填 6 个 0 勾选已实现变更（仅勾自动化已验证项，人工关卡保留未勾）
- add-context-length-config 补实现（原实现缺失、验证报告失实）并重写失实报告
- `openspec validate --all` **36/36 通过**

## 2. 当前状态

| 指标 | 值 |
|---|---|
| 活跃变更 | 14 |
| 已归档 | 16 + 去重 1 |
| 主规范 capability | 22 |
| 工作区未提交 | 仅 harden WIP（见 §4） |

## 3. 剩余 14 个活跃变更（全部卡在人工门禁，无法自动化）

| 变更 | 任务 | 卡点 | 后续操作 |
|---|---|---|---|
| add-custom-llm-api | 64/66 | 9.6 真实 LLM 手动验证、9.7 落验证报告 | **优先级最高**：有真实 key 即可完成 → 归档（spec 已同步、其余全勾） |
| harden-llm-output-validation | 42/43 | 6.5 真实 LLM 全栈深度分析 | 验证报告已存在（2026-08-03，605 passed），补 6.5 后归档 |
| enable-deepseek-thinking-mode | 32/34 | 7.5 nightly @live、7.6 人工 ADR（agent 不得新建） | 人工落 ADR 后归档；7.5 属 nightly 长期 |
| harden-evaluation-rigor | 17/20 | 3 项人工门禁（ADR / 双人标注基准集 / 消融真实跑批） | 当前 feat 分支工作的收尾，人工门禁完成后归档 |
| langfuse-trace-agent-attribution | 16/18 | 3.2 / 4.6 实跑 Langfuse 对账（post-merge 才能做） | 合并后实跑对账 → 归档 |
| decision-outcome-tracking | 11/13 | 前置人工 ADR、落库口径（approve-only 待确认） | 落 ADR + 确认口径后归档 |
| agent-evaluation-suite | 10/12 | 校准 ≥80%（Annotation Queue 人工打分）、线上托管 Evaluator | 人工校准后归档 |
| restore-session-on-refresh | 13/15 | 4.3 E2E 门禁、4.4 人工验证（交互类） | E2E + 人工验证后归档 |
| fix-stream-event-routing | 11/13 | 5.3 E2E 门禁、5.4 人工验证（交互类） | 同上 |
| data-ordering-citation-contract | 9/10 | 3.2 实跑对账 + 验证报告（2.4 已核实） | 实跑对账后归档 |
| refactor-frontend-stream-store | 21/58 | tasks 大量未勾 + stream-store 主规范已建但需回填 + 无验证报告 + ADR/incidents | 属进行中重构，非本次清理范围 |
| fix-analysis-ux-polish | 0/15 | 实现基本在但未收口（无 tasks 回填/验证/主规范 backend 缺失） | 需先收口实现再走归档流程 |
| transparent-system-events | 0/21 | 未实现（rules/ 缺失，全仓 0 命中） | 需先实现 |
| fix-citation-contract-diseases | 0/5 | 工作区 WIP（见 §4） | 用户进行中 |

## 4. 未提交的 harden WIP（本分支遗留，未推送）

以下属 `harden-evaluation-rigor` / `fix-citation-contract-diseases` 进行中的工作，**刻意未提交**（含失败测试，不符合提交标准）：

```
M  src/finance_agent/citation.py
?? openspec/changes/fix-citation-contract-diseases/
?? scripts/evals_gated_run.py
?? scripts/observe_langfuse_experiments.py
?? tests/scripts/_probe_journal_tokens.py
?? tests/test_citation_contract.py
```

> ⚠️ 全量非 live 测试当前 **3 个失败**，全部在 `tests/test_citation_contract.py`（未跟踪）——即 fix-citation-contract-diseases 正在开发的测试。接手者须先完成该 delta 再处理。
>
> 另外：ruff 全仓 **11 错**全在 `scripts/evals_gated_run.py` 与 `scripts/observe_langfuse_experiments.py`（未跟踪）；mypy 基线 **69 错**为仓库已知状态（CI 用 `mypy src/ || true` 容忍）。

## 5. 关键决策与红线（接手者务必遵守）

1. **主规范库是唯一真相来源**：只经 delta sync 合并，禁止手改（AGENTS.md 红线）。本分支的 sync 均为按 openspec-sync-specs 技能智能合并（保留 delta 未提的既有场景），归档用 `openspec archive <id> -y --skip-specs`（spec 已手动同步时）。
2. **不虚勾 tasks、不伪造验证报告**：add-context-length-config 的教训——原报告引用的测试不存在。本次所有回填仅勾「自动化已验证」项，人工关卡一律保留未勾；验证报告如实标注 ⬜ 待真实环境项。
3. **人工 ADR（enable-deepseek / decision-outcome / harden-evaluation-rigor）agent 不得新建**，须人工维护（AGENTS.md）。
4. **mypy 基线 69 错**：验收按「基线对比无新增」惯例，CI 已容忍。
5. **LLM 家族 capability 的 MODIFIED delta 相互叠加**（llm-provider-gateway 由 5 个变更修改）：合并需按依赖序（基座 ADDED → 后续 MODIFIED），不得丢场景。

## 6. 下一步建议（按优先级）

1. **add-custom-llm-api**（64/66）：真实 LLM key 验证 9.6 → 落报告 9.7 → 归档。投入产出最高。
2. **harden-llm-output-validation**（42/43）：真实 LLM 全栈跑 6.5 → 归档。
3. **合并后实跑 Langfuse 对账**：langfuse-trace（3.2/4.6）、data-ordering（3.2）、decision-outcome（口径确认）——现在已推入 main，可实跑。
4. **人工落 ADR**：enable-deepseek（7.6）、decision-outcome、harden-evaluation-rigor。
5. **agent-evaluation-suite**：Annotation Queue 校准 ≥80% + 托管 Evaluator。
6. **交互类 E2E + 人工验证**：restore-session-on-refresh、fix-stream-event-routing。
7. **fix-citation-contract-diseases**：完成当前 WIP（先让 test_citation_contract.py 3 个失败转绿）→ 补验证报告 → 归档。

## 7. 参考

- 完整审计报告：`docs/audit/2026-08-28-openspec-archive-audit.md`
- 归档清单：`openspec/changes/archive/2026-08-28-*`
- 主规范库：`openspec/specs/`（22 个 capability）
- 验证报告：`tests/validation/2026-08-28-*.md`（新增 6 份，含 context-length 重写）
