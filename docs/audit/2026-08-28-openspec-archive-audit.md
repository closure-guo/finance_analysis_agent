# OpenSpec Delta 实现与归档审计报告

- 日期: 2026-08-28
- 分支: `audit/openspec-archive-sweep`（自 `feat/harden-evaluation-rigor` 拉出）
- 范围: `openspec/changes/` 全部活跃 delta 变更（起始 31 个，处理后 28 个）
- 方法: 4 个并行只读审计代理逐变更核验实现（spec↔代码）、验证报告、主规范同步、tasks 勾选、`openspec validate --strict`

---

## 1. 本次已处理（sync + archive 进展，截至审计日）

### 第一批（前轮审计收尾）
| 变更 | 动作 | 依据 |
|---|---|---|
| thinking-stream-banner-display | 归档 → `archive/2026-08-28-…` | 四关全过：tasks 28/28、主规范已同步、验证报告 ✓、validate ✓ |
| hide-tool-use-banner-during-web-search | 归档 → `archive/2026-08-28-…` | 四关全过：tasks 12/12、主规范已同步、验证报告 ✓、validate ✓ |
| improve-decision-grounding | 删除活跃残留（`git rm`） | 与 `archive/2026-08-24-improve-decision-grounding` 逐字节相同，archive 已完成但活跃副本未删 |

### 第二批（sync 大会战）
| 变更 | 动作 | sync 内容 |
|---|---|---|
| fix-pipeline-banner-and-eta | `openspec archive`（自动 sync） | frontend +1/～3（Pipeline ETA Display） |
| fix-history-report-anchor | `openspec archive`（自动 sync） | session-persistence +1、frontend 锚点表述更新 |
| fix-node-timer-real-lifecycle | 手动 sync 后 `archive --skip-specs` | frontend 追加 3 计时场景、pipeline-events 新增「节点生命周期真实时间戳」 |
| redesign-pipeline-hierarchical-timeline | 手动 sync 后 `archive --skip-specs` | frontend「Pipeline Progress Display」替换为分层时间轴、Thinking Display 按子节点归入 |
| remove-evals-local-nonlangfuse-path | 手动 sync 后 `archive --skip-specs` | evaluation 新增 6 基础 requirement（确定性评估器/Judge/Dataset/实验回归/校准/托管），其中「实验回归工作流」采用含无 Langfuse 显式报错的增强版 |

> 说明：`openspec archive` 对 MODIFIED delta 有严格检查（防丢场景）。对演化中的主规范，需先按 openspec-sync-specs 技能**手动智能合并**（保留 delta 未提及的既有场景），再用 `--skip-specs` 归档。

### 第三批（sync 大会战完成）
- **LLM 家族主规范 sync**：新建 7 个 capability 主规范（llm-provider-gateway、llm-config、llm-budget-governance、llm-capability-probe、llm-mode-gating、llm-policy-router、llm-output-contract），从 add-llm-provider-gateway（ADDED 基座）+ harden/align/migrate 的 MODIFIED 智能合并；**add-context-length-config 因实现缺失按指示未 sync**。
- **trace-observability sync**：合并 add-llm-provider-gateway + langfuse-trace-agent-attribution + agent-trace-content-fidelity 三个 delta，从 4 扩到 15 requirement。
- **evaluation 主规范**：并入 agent-evaluation-suite 的 6 个基础 requirement（含 remove-evals 增强版「实验回归工作流」）。
- **harden-llm-gateway-governance 归档**（tasks 9/9 + 验证报告 ✓，sync 后归档）。

**主规范库**：11 → 18 个 capability，`openspec validate --all` 40/40 通过。

## 1b. 本会话最终状态（2026-08-28 收尾）

| 类别 | 数量 | 说明 |
|---|---|---|
| 已归档 | **16** | thinking-stream-banner-display、hide-tool-use-banner-during-web-search、fix-pipeline-banner-and-eta、fix-history-report-anchor、fix-node-timer-real-lifecycle、redesign-pipeline-hierarchical-timeline、remove-evals-local-nonlangfuse-path、harden-llm-gateway-governance、migrate-off-legacy-llm-shim、align-ark-glm-param-defaults、add-llm-api-form、agent-trace-content-fidelity、add-report-export、add-context-length-config（补实现后）、add-llm-provider-gateway、truncation-resume-generation |
| 重复已删 | 1 | improve-decision-grounding（archive 已有 2026-08-24 副本） |
| 主规范库 | 11 → 22 | 新增 llm-* 11 个 + report-export，合并 evaluation/trace-observability/frontend/pipeline-events/session-persistence 内容 |
| 新增/重写验证报告 | 6 | 2026-08-28-{migrate, align, add-llm-api-form, truncation}-validation.md + add-context-length-config 失实报告重写 |
| 活跃变更 | **14** | 全部卡在「真实 LLM / 真实 Langfuse 对账 / ADR（agent 不得新建）/ 校准 ≥80% / E2E 门禁」等硬性人工关卡，或属未实现 / in-progress 功能工作 |
| 提交 | 3 | 542a009（归档+sync+回填+审计）、2d5fcc9（context-length 实现）、0bd6684（再归档 2 个） |

**sync 大会战已完成**：主规范库覆盖全部 delta 能力域；add-context-length-config 已按用户决策补实现（TDD）+ 重写失实报告 + 归档。

### 剩余 14 个活跃变更（全部需人工/真实环境）
| 卡点 | 变更 |
|---|---|
| 真实 LLM 人工验证 | add-custom-llm-api（9.6/9.7）、harden-llm-output-validation（6.5）、enable-deepseek-thinking-mode（7.5） |
| 人工 ADR（agent 不得新建） | enable-deepseek-thinking-mode（7.6）、decision-outcome-tracking（前置）、harden-evaluation-rigor（1 项） |
| 真实 Langfuse 对账 | langfuse-trace-agent-attribution（3.2/4.6） |
| E2E + 人工验证（交互类） | restore-session-on-refresh（4.3/4.4）、fix-stream-event-routing（5.3/5.4） |
| 校准 ≥80% + 托管 Evaluator | agent-evaluation-suite（2 项） |
| 实跑对账 | data-ordering-citation-contract（3.2；2.4 已核实） |
| in-progress | harden-evaluation-rigor（17/20，当前分支工作）、refactor-frontend-stream-store（21/58） |
| 未实现 | transparent-system-events（0/21）、fix-analysis-ux-polish（0/15 部分） |
| 进行中（用户 WIP） | fix-citation-contract-diseases（0/5，工作区未提交，含 3 个失败测试） |

## 2. 总览矩阵（28 个活跃变更）

| 变更 | tasks | 实现 | 主规范同步 | 验证报告 | 归档结论 |
|---|---|---|---|---|---|
| **卡「实现缺失」** | | | | | |
| add-context-length-config | 3/3 勾 | **未见**（contextLength/LLM_MAX_CONTEXT 全库 0 命中，验证报告引用的测试均不存在） | ✗ | 有但**失实** | 先补实现或撤 delta |
| **卡「全部关卡 / 未收口」** | | | | | |
| transparent-system-events | 0/21 | 未见（rules/ 缺失，全仓 0 命中） | ✗ | 无 | 未实现 |
| fix-analysis-ux-polish | 0/15 | 部分（4 行为代码已落地，未收口） | ✗（backend 主规范缺失） | 无 | tasks/验证/E2E/主规范未闭合 |
| fix-citation-contract-diseases | 0/5 | 进行中（工作区未提交） | ✗ | 无 | 未完成（新建） |
| **卡「主规范未同步」（tasks 已全勾，补 sync 即可归档）** | | | | | |
| remove-evals-local-nonlangfuse-path | 7/7 | ✓ | 部分（Requirement 未真正并入主库） | 无（任务未要求） | 补 sync 后归档 |
| fix-history-report-anchor | 17/17 | ✓ | ✗（frontend/spec.md:275 旧表述） | ✓ | 卡 sync |
| redesign-pipeline-hierarchical-timeline | 17/17 | ✓ | ✗（Pipeline Progress 旧 6 圆点） | ✓ | 卡 sync |
| fix-pipeline-banner-and-eta | 19/19 | ✓ | ✗（ETA requirement 未并入） | ✓ | 卡 sync |
| fix-node-timer-real-lifecycle | 12/12 | ✓ | 部分（frontend ✓、pipeline-events ✗） | ✓ | 卡 sync |
| migrate-off-legacy-llm-shim | 13/13 | ✓ | ✗（llm-provider-gateway 主规范缺失） | 无 | 卡 sync + 验证报告 |
| align-ark-glm-param-defaults | 10/10 | ✓ | ✗（同上） | 无 | 卡 sync + 验证报告 |
| add-llm-api-form | 8/8 | ✓ | ✗（llm-config 主规范缺失） | 无 | 卡 sync + 验证报告 |
| harden-llm-gateway-governance | 9/9 | ✓ | ✗（5 capability 主规范全部缺失） | ✓ | 卡 sync |
| **卡「tasks 未全勾 / 未回填」+ 主规范未同步** | | | | | |
| add-llm-provider-gateway | 22/23 | ✓ | ✗（4 capability 缺失/部分） | ✓ | 卡 5.4 + sync |
| add-custom-llm-api | 64/66 | ✓ | ✗（llm-config 缺失） | 无 | 卡 9.6/9.7 + sync |
| truncation-resume-generation | 12/13 | ✓ | ✗（llm-output-resume 缺失） | 无 | 卡 4.3 + sync |
| enable-deepseek-thinking-mode | 32/34 | ✓ | ✗（llm-thinking-mode 缺失） | 无 | 卡 7.5/7.6(ADR) + sync |
| harden-llm-output-validation | 42/43 | ✓ | ✗（agent-node-contracts 缺失） | ✓ | 卡 6.5 + sync |
| restore-session-on-refresh | 13/15 | ✓ | ✗ | 无 | 卡 4.3/4.4 + sync |
| fix-stream-event-routing | 11/13 | ✓ | ✗ | 无 | 卡 5.3/5.4 + sync |
| refactor-frontend-stream-store | 21/58 | ✓（已接入） | ✗（stream-store 缺失） | 无 | 卡 tasks + sync + ADR/incidents |
| data-ordering-citation-contract | 0/10 | ✓（9 测试过） | ✗（citation-verification/data-fetching 缺失） | 无 | 卡 tasks 0/10 回填 + sync |
| langfuse-trace-agent-attribution | 0/18 | ✓（36 测试过） | ✗（trace-observability 内容未合并） | ✓ | 卡 tasks 0/18 回填 + sync |
| add-report-export | 0/13 | ✓（11 测试过） | ✗（report-export 缺失 + frontend 未合并） | ✓（部分待人工） | 卡 tasks 0/13 回填 + sync |
| agent-evaluation-suite | 0/12 | ✓（188 测试过） | ✗ | ✓（待人工） | 卡 tasks 回填 + sync + 人工验证 |
| decision-outcome-tracking | 0/13 | ✓（64 测试过） | ✗（decision-outcome 缺失） | ✓（待人工） | 卡 tasks 回填 + sync + ADR |
| agent-trace-content-fidelity | 0/9 | ✓ | ✗ | ✓（待人工） | 卡 tasks 回填 + sync + 人工验证 |
| harden-evaluation-rigor | 17/20 | ✓（115 测试过） | ✗（citation-verification/decision-backtest 缺失） | ✓（3 项待人工） | 卡 3 项人工门禁 + sync |

## 3. 结构性发现

### 3.1 主规范库严重欠同步（红线问题，优先级最高）
`openspec/specs/` 仅 11 个 capability，而 28 个活跃变更引用的能力中至少 **15 个 capability 在主规范中缺失或内容未合并**：`llm-provider-gateway`、`llm-config`、`llm-budget-governance`、`llm-capability-probe`、`llm-mode-gating`、`llm-policy-router`、`llm-output-contract`、`llm-output-resume`、`llm-thinking-mode`、`agent-node-contracts`、`report-export`、`citation-verification`、`decision-backtest`、`decision-outcome`、`data-fetching`、`stream-store`、`transparent-system-events`、`backend`。另有 `frontend`/`trace-observability`/`evaluation`/`pipeline-events` 等主 spec 文件存在但**内容级未合并**（多处仍是旧表述）。

按 AGENTS.md 红线「主规范是唯一真相来源、只经 delta sync 合并，禁止手改」，这些 delta 的契约尚未真正进入主规范库，是归档的最大共同卡点。

### 3.2 tasks.md 回填严重不一致
6 个变更实现完整、测试全绿、有实现提交，但 tasks.md **0 项勾选**（从未回填）：
`agent-evaluation-suite`、`decision-outcome-tracking`、`agent-trace-content-fidelity`、`data-ordering-citation-contract`、`langfuse-trace-agent-attribution`、`add-report-export`。
另有多个只差 1-3 项人工门禁未勾（`truncation-resume-generation` 4.3、`add-custom-llm-api` 9.6/9.7、`harden-evaluation-rigor` 3 项、`enable-deepseek-thinking-mode` 7.5/7.6、`harden-llm-output-validation` 6.5、`restore-session-on-refresh` 4.3/4.4、`fix-stream-event-routing` 5.3/5.4）。

### 3.3 add-context-length-config：验收记录失实（最严重单项）
tasks 3/3 全勾 + 有验证报告 + `openspec validate --strict` 通过，但功能在代码中**从未落地**：
- `src/` 与 `frontend/src/` 全库 grep `contextLength` / `LLM_MAX_CONTEXT` 零命中；
- 验证报告引用的测试（`TestContextLengthOverride` 等）均不存在；
- 追溯引入提交 `0fa8099`，`contextLength` 也只存在于 openspec 工件与验证报告，从未进入源码。

→ 归档门禁的 `validate --strict` 与勾选状态都不查真实实现。这正是「未验证就 archive = 把意图当真相写入基线」的反例，须先补实现或撤销该 delta。

### 3.4 验证报告普遍含「待人工」项
`agent-evaluation-suite`、`decision-outcome-tracking`、`agent-trace-content-fidelity`、`add-report-export`、`harden-evaluation-rigor` 的验证报告均标注了真实 LLM / Langfuse UI / 真实行情 / ADR 等未完成项，与「人工验证报告已落」的 archive 前置不符。`migrate-off-legacy-llm-shim`、`align-ark-glm-param-defaults`、`add-llm-api-form`、`add-custom-llm-api`、`truncation-resume-generation`、`enable-deepseek-thinking-mode`、`restore-session-on-refresh`、`fix-stream-event-routing`、`refactor-frontend-stream-store`、`data-ordering-citation-contract`、`transparent-system-events`、`fix-analysis-ux-polish` 则完全没有验证报告。

### 3.5 其他
- `migrate-off-legacy-llm-shim`、`align-ark-glm-param-defaults`、`add-context-length-config` 缺 `design.md`，`openspec status` 判 `isComplete=False`（不影响 `validate --strict`）。
- `enable-deepseek-thinking-mode` 的人工 ADR 未落 `docs/adr/`。
- `refactor-frontend-stream-store` 的 ADR 与 incident 记录缺失。
- 实现质量总体良好：除 add-context-length-config、transparent-system-events 外，其余变更的 spec requirement 均有对应代码，抽查 500+ 测试全部通过。

## 4. 后续行动建议（按优先级）

1. **主规范 sync 大会战**：对 15 个缺失 capability 的变更逐一执行 `openspec-sync-specs`（含新建 capability 主 spec），消除最大卡点。这是批量、低风险、可并行的机械操作。
2. **撤/补 add-context-length-config**：二选一——补实现 + 重写验证报告，或删除该 delta 与失实验证报告。
3. **tasks.md 回填**：6 个「0 勾选但已实现」变更按实现事实回填；其余差人工门禁的逐项补齐。
4. **验证报告补全**：未落报告的实现变更补齐；含「待人工」项的按需完成或明确降级为已知限制。
5. **重复与残留清理**：已确认 `improve-decision-grounding` 唯一重复已清理；后续 sync+archive 每个变更后必须确认活跃目录移除。

## 5. 附注
- 工作区存在未提交改动（`src/finance_agent/citation.py`、`openspec/changes/fix-citation-contract-diseases/`、`scripts/evals_gated_run.py`、`scripts/observe_langfuse_experiments.py`、`tests/test_citation_contract.py`），属 `harden-evaluation-rigor` 分支进行中的工作，与本次审计无关。
- 本次审计动作（2 归档 + 1 去重）尚未提交，`git status` 显示为 staged 的 R/D。
