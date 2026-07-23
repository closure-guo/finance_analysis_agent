# OpenSpec + Superpowers 实施文档

> 项目：closure-guo/finance_analysis_agent
> 目标：将现有 Matt Pocock skills 体系迁移为 **OpenSpec（契约状态机）+ Superpowers（执行纪律）** 双框架工作流
> 版本：v2.0 · 2026-07-23（按架构讨论结论修订：Trae 侧按论坛帖方式接入 Superpowers；规则入口以 AGENTS.md 为准；基线构建后置）

---

## 1. 背景与目标

### 1.1 现状

仓库当前基于 Matt Pocock skills 建立了文档与执行体系：

```
执行层（待替换）：
  .trae/skills/          ← MP skills 全套（tdd / triage / grill-me 等 19 个目录，
                           混有少量 Superpowers 风格 skill）
  .claude/skills/        ← 仅剩 README.md（skills 本体已不在）

文档资产（保留，与工具无关）：
  CONTEXT.md                     ← 项目级架构记忆
  docs/adr/0001 ~ 0017           ← 17 篇架构决策记录
  docs/agents/                   ← issue-tracker / triage-labels / domain 配置
  docs/PRD.md、architecture.md
  docs/design/                   ← 专项设计文档
  docs/incidents/001 ~ 010       ← 事故记录

接线点（待改写）：
  AGENTS.md                      ← 规则入口（路由 + 红线），本文件 §6 改写稿
  .trae/rules/project_rules.md   ← Trae 侧注入规则，同步红线与路由简版
```

> 注：不存在 `skills-lock.json`；`.claude/skills/` 仅残留 README，清理时一并删除。

### 1.2 要解决的两个真实短板

| 短板 | 根因 | 由谁解决 |
|---|---|---|
| 「测试全过但交互逻辑有 bug」（incident 005/010 类事故） | 缺少行为级验证纪律 | **Superpowers**：红-绿 TDD、review 关卡、verification-before-completion |
| 修改已有行为时 agent 凭幻觉发挥 | 缺少「系统当前应该是什么样」的基准 | **OpenSpec**：主规范库 + delta 提案 + 合并归档 |

### 1.3 核心概念修正

**Superpowers 没有等价的文档架构来接管 MP 体系。** 它的产物是任务级耗材（`docs/superpowers/` 下的 specs/plans，做完即归档），不会维护 CONTEXT.md 和 ADR。因此本次迁移的正确动作是：

- **换执行纪律层**：MP skills → Superpowers
- **保留文档资产**：CONTEXT.md、ADR、incidents 原样保留
- **新增契约层**：OpenSpec 主规范库 + delta 机制
- **ADR 书写转为手动约定**（这本来就是该由人把关的事）

---

## 2. 总体架构

```
┌─────────────────────────────────────────────────────────┐
│ 路由层：AGENTS.md（dispatcher 规则，见 §6 改写稿）          │
│   .trae/rules/project_rules.md 同步红线 + 路由简版          │
├─────────────────────────────────────────────────────────┤
│ 契约层：OpenSpec                                         │
│   openspec/specs/     主规范库（系统当前行为的唯一真相）      │
│   openspec/changes/   变更提案（delta：ADDED/MODIFIED/REMOVED）│
│   openspec/archive/   已合并的历史变更                      │
├─────────────────────────────────────────────────────────┤
│ 执行层：Superpowers（.trae/skills/ 手动安装）               │
│   writing-plans → TDD subagent 执行 → review → verification │
│   产物落在 docs/superpowers/（任务级耗材）                   │
├─────────────────────────────────────────────────────────┤
│ 文档资产层（保留不动）                                      │
│   CONTEXT.md · docs/adr/ · docs/incidents/ · docs/design/  │
└─────────────────────────────────────────────────────────┘
```

**分工一句话**：OpenSpec 管「行为契约的流转」（propose → apply → archive），Superpowers 管「执行纪律」（契约到手之后怎么写代码、怎么验证），AGENTS.md 管「什么情况走哪条路」。

---

## 3. 迁移步骤

### Step 1：卸载 MP skills（约 30 分钟）

```powershell
# 删除 MP skills 全套与残留
Remove-Item -Recurse -Force .trae/skills/
Remove-Item -Recurse -Force .claude/skills/

git add -A; git commit -m "chore: remove matt-pocock skills, preparing for superpowers migration"
```

> MP skill 均为自包含目录，无反向依赖，删除不影响任何文档。
> triage / to-issues 等 GitHub 工作流类 skill 无 Superpowers 等价物，其流程要点改写为 AGENTS.md 规则文本（见 §6）。

### Step 2：安装 Superpowers（Trae 手动接入，约 1 小时）

Superpowers 官方支持 Claude Code / Codex / Cursor 等，**不含 Trae**。经评估采用 Trae 论坛集成方案（https://forum.trae.cn/t/topic/15519 ），即手动安装：

```powershell
# 克隆源码
git clone https://github.com/obra/superpowers.git $env:TEMP/superpowers

# 拷贝 skills 到 Trae 技能目录
Copy-Item -Recurse $env:TEMP/superpowers/skills/* .trae/skills/
```

然后在 Trae 中创建三个 subagent（提示词模板见论坛帖原文）：

| Subagent | 职责 |
|---|---|
| `spec-reviewer` | 对照 spec 逐行验证实现，不信任实施者报告 |
| `implementer` | 按任务卡实施 + 自审 + 结构化汇报（DONE / DONE_WITH_CONCERNS / BLOCKED / NEEDS_CONTEXT） |
| `code-quality-reviewer` | spec 合规通过后做代码质量审查（Critical / Important / Minor 分级） |

**已知代价与补偿**：手动安装失去插件 hooks 与 dispatcher 强制注入。补偿手段是把「任务进站先分类、新功能必须先走 OpenSpec delta」写成 `.trae/rules/project_rules.md` 硬规则——rules 每次会话必注入，可部分替代 dispatcher。

**验证（最小冒烟）**：开启新会话随意提一个小任务，确认 agent 能主动声明走哪个 skill、能调用 `using-superpowers`。若 Trae 侧验证不通过（论坛评论区报告过 subagent 授权、脚本执行受限等问题），回退到备选方案：agent 工作流回 Claude Code，Trae 仅作编辑器。

### Step 3：初始化 OpenSpec 并构建基线（后置，单独迭代）

本轮迁移**不执行本步**，待 Step 1/2/4 完成并验证后单独立项。届时：

```bash
npm install -g @fission-ai/openspec   # 或按官方文档最新方式安装
openspec init
```

基线**首轮只做 `frontend/` 一个领域**（incident 010 事故高发区，React chat UI 交互行为），即投用即验证；后续按 scoring → data-pipeline → agents → 其余领域的顺序分批补齐。原料现成：CONTEXT.md + architecture.md + 17 篇 ADR + 10 篇 incidents 可逐领域反推。让 agent 起草、人逐篇审。

候选基线目录（按仓库五层架构与 ADR 划分，可按需调整）：

```
openspec/specs/
├── frontend/             ← React chat UI 交互行为（首轮，事故高发区）
├── scoring/              ← ADR-0003 双阈值评分、incident 005 GARP/杜邦口径
├── data-pipeline/        ← ADR-0001 数据准备节点、AKShare 数据源约定
├── agents/               ← ADR-0002 pure-LLM agents、ADR-0010 tool-use 重构
├── report/               ← ADR-0007 综合报告结构
├── api-streaming/        ← ADR-0012 session 流式与自然输入
├── persistence/          ← ADR-0004 分层持久化
├── mcp-server/           ← ADR-0008
└── observability/        ← ADR-0015/0016 Langfuse tracing 与 prompt 管理
```

**每篇 spec 的写作要求**：

- 用 `## ADDED Requirements` 风格的需求条目 + `#### Scenario:` 场景描述（与 delta 格式同源，方便日后 MODIFIED/REMOVED 操作）
- 只描述**行为契约**（给定 X 输入，系统必须 Y），不写实现细节
- 每个领域 spec 头部注明来源 ADR 编号，保持可追溯

### Step 4：改写 AGENTS.md（约 1 小时）

将现有 "Agent skills" 章节替换为 §6 改写稿；其余章节保持不变。同步更新 `.trae/rules/project_rules.md`（红线 + 路由简版）。

### Step 5：跑通全流程验证（约半天，随 Step 3 一并执行）

把 `docs/incidents/005-garp-dupont-test-pollution` 这类已解决事故**翻译成一个模拟 delta 提案**，完整走一遍：提案 → writing-plans → TDD → 验证 → sync + archive。目的是在真实需求到来之前，先把管线的每个关卡踩实。

---

## 4. 工作流路由规则

所有任务进站前先分类，**这是整个体系的 dispatcher**：

| 任务类型 | 路由 | 是否触碰 OpenSpec |
|---|---|---|
| 新功能 | delta 提案 → Superpowers（从 writing-plans 进）→ 验证 → sync + archive | ✅ 全程 |
| 修 bug · 意图不变（spec 对、代码错） | Superpowers `systematic-debugging` + 复现测试红线 | ❌ 不碰 |
| 修 bug · 意图变更 / 行为从未定义 | 同新功能流程（先写 delta 定义「应该是什么样」） | ✅ 全程 |
| 重大架构决策 | 手动落 `docs/adr/`（编号递增，只增不改） | ❌ |
| 小改动（typo、文案、配置） | 直接改，不走任何管线 | ❌ |

**两类 bug 的判别标准**：打开主规范库对应条目——如果「正确行为」已写在里面而代码没做到，是 A 类；如果翻不到对应条目、或条目本身要改，是 B 类。incident 005 即为典型 B 类。

---

## 5. 新功能完整流程（SOP）

### 5.1 管道总览

```
需求清晰吗？
  ├─ 不清晰 → 先由人澄清（可用 Superpowers brainstorming，仅限人脑对齐阶段）
  ↓
① OpenSpec 提案：openspec/changes/NNN-特性名/
     ├── delta spec      ← 行为契约：ADDED / MODIFIED / REMOVED
     └── tasks.md        ← 粗粒度验收 checklist
  ↓ 【delta 出站，writing-plans 进站】
② Superpowers（跳过 brainstorming/spec，从 writing-plans 进入）
     writing-plans       ← 读 delta，拆成 TDD 粒度的执行计划
     → 每任务新 subagent 执行（红-绿 TDD）
     → code review → verification-before-completion
  ↓ 【验证关卡通过】
③ OpenSpec 收尾
     sync                ← delta 合并进 openspec/specs/ 主规范库
     → archive           ← changes/NNN-x 按日期归档
```

### 5.2 关键规则

**规则 1：契约归 OpenSpec，施工图归 Superpowers。**
delta spec 已经承担了 what/why 的职责，**Superpowers 管线绝不再从 brainstorming 进**，否则同一份需求写两遍、两份文档漂移。

**规则 2：两份任务列表分层，不合并。**
- OpenSpec 的 `tasks.md`：粗粒度验收项（如「流式中断恢复可用」），执行中回填勾选，archive 前必须全勾
- Superpowers 的 plan：细粒度 TDD 步骤，做完即弃，不回填

tasks.md 是 delta 契约与 archive 关卡之间的桥梁。

**规则 3：archive 是「合并已验证的事实」，不是「归档提案」。**
sync 会把 delta 真正写进主规范库。若未验证就 archive，等于把「意图」当「真相」写入基线——incident 005 的文档版。

### 5.3 archive 前置检查清单（硬关卡）

```
archive 前必须全部满足：
  □ openspec/changes/NNN-x/tasks.md 全部勾选
  □ Superpowers verification-before-completion 已通过
  □ 人工验证报告已落 tests/validation/（沿用仓库现有约定）
  □ openspec validate --strict 通过
```

### 5.4 并行变更

不同 requirement 的提案可并行推进；同一 requirement 被两个提案同时 MODIFIED 时，后到者必须 rebase 到先到者的合并结果上（sync 后主规范库是唯一真相，以它为准解决冲突）。

---

## 6. AGENTS.md 改写稿

将现有 "Agent skills" 章节整体替换为以下内容（其余章节——测试产物位置、incident tracking、常用命令等——保持不变）：

```markdown
## Workflow routing

所有任务进站前先分类（详见 docs/openspec-superpowers-实施文档.md §4）：

- **新功能** → OpenSpec delta 提案（openspec/changes/）→ Superpowers 管线
  （从 writing-plans 进入，跳过 brainstorming）→ 验证 → sync + archive
- **修 bug · 意图不变** → 复现测试 + superpowers:systematic-debugging，
  不触碰 openspec
- **修 bug · 意图变更 / 行为未定义** → 同新功能流程，delta 先行
- **重大架构决策** → 手动落 docs/adr/（编号递增，只增不改）
- **小改动** → 直接改

## Spec contract rules

- openspec/specs/ 是系统当前行为的唯一真相来源；修改任何已有行为前必须先查它
- delta 提案是契约的唯一编辑入口；主规范库只能通过 sync 合并更新，禁止手改
- Superpowers 管线的输入是 delta spec，不是对话记录

## Verification red lines

- 没有先写失败测试的代码，删除重写
- archive 前置条件：tasks.md 全勾 + verification 通过 + 人工验证报告落
  tests/validation/
- 「测试全过」不等于「行为正确」；交互行为变更必须有人工验证环节

## Agent skills

### Issue tracker
Issues tracked on GitHub. Use `gh` CLI for all operations. See docs/agents/issue-tracker.md.

### Triage labels
See docs/agents/triage-labels.md.

### Domain docs
Single-context layout — one CONTEXT.md + docs/adr/ at the repo root.
See docs/agents/domain.md. ADR 由人手动维护，agent 不得自动新建 ADR。
```

`.trae/rules/project_rules.md` 同步上述三节中的**红线与路由简版**（详细规则以 AGENTS.md 为准，避免双份漂移）。

---

## 7. 目录结构约定（迁移完成后）

```
finance_analysis_agent/
├── AGENTS.md                    ← 路由规则 + 红线（§6 改写稿）
├── CONTEXT.md                   ← 保留，项目级架构记忆
├── openspec/                    ← 【后置，Step 3 时创建】
│   ├── specs/                   ← 主规范库（首轮仅 frontend/）
│   ├── changes/                 ← 进行中的 delta 提案
│   └── archive/                 ← 已合并的历史变更
├── docs/
│   ├── openspec-superpowers-实施文档.md   ← 本文件
│   ├── adr/0001~0017+           ← 保留，手动递增
│   ├── agents/                  ← 保留（issue-tracker / triage-labels / domain）
│   ├── incidents/               ← 保留，持续记录
│   ├── design/                  ← 保留
│   ├── superpowers/             ← Superpowers 任务级产物（耗材，可定期清理）
│   ├── PRD.md、architecture.md  ← 保留
├── tests/validation/            ← 人工验证报告（archive 前置条件之一）
└── （已删除：.claude/skills/；.trae/skills/ 内容替换为 Superpowers skills）
```

---

## 8. 风险与注意事项

| 风险 | 说明 | 对策 |
|---|---|---|
| Trae 手动安装 Superpowers 能力受限 | 失去插件 hooks 与 dispatcher 强制注入；论坛反馈 subagent 授权、脚本执行可能受限 | Step 2 末尾做最小冒烟验证；不通过则回退「工作流回 Claude Code」备选方案 |
| dispatcher 缺失导致纪律松弛 | 手动拷贝版全靠 rules 注入与 agent 自觉 | 路由表与红线写进 .trae/rules/project_rules.md（每次会话必注入） |
| ADR 断更 | 删除 MP skills 后无机制自动写 ADR | AGENTS.md 立规：重大决策手动落 ADR，人把关 |
| 基线 bootstrap 烂尾 | 1~2 天的重活，最容易半途而废 | 后置到单独迭代；首轮只做 frontend/ 一个领域，即投用即验证 |
| 验证关卡被绕 | 「测试绿了」的冲动会诱惑跳过人工验证 | archive 前置清单写进 AGENTS.md 红线，agent 无权豁免 |
| Superpowers 路由过度触发 | 小任务也被拽进完整管线 | 路由表明确「小改动直接改」；必要时在 AGENTS.md 加豁免场景 |
| Token 开销上升 | 完整管线比 MP 单发 skill 重 | 只在路由表命中的场景走全流程；小任务保持轻量 |

---

## 9. 迁移检查清单

本轮（Step 1/2/4）：

```
□ Step 1  删除 .trae/skills/（MP 全套）、.claude/skills/（残留 README），提交
□ Step 2  按论坛帖拷贝 Superpowers skills 到 .trae/skills/，
          创建 spec-reviewer / implementer / code-quality-reviewer 三个 subagent；
          新会话冒烟验证 skill 可被调用
□ Step 4  AGENTS.md 按 §6 改写；.trae/rules/project_rules.md 同步红线与路由简版；提交
```

下一轮（Step 3/5，单独立项）：

```
□ Step 3  openspec init；首轮仅构建 frontend/ 领域基线并投用
□ Step 5  用 incident 005 做模拟提案，完整跑通 提案→执行→验证→sync+archive
□ 第一个真实新功能按 §5 SOP 执行，复盘管道卡点
```

**预估耗时**：本轮 Step 1/2/4 合计约 2.5 小时；下一轮 Step 3 基线（首轮单领域）约半天、Step 5 半天。
