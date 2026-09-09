# 明日方舟 UI 主题换肤设计（update-arknights-ui-theme）

> 日期：2026-09-08｜状态：已定稿（用户浏览器预览确认）｜关联 delta：`openspec/changes/update-arknights-ui-theme/`

## 1. 背景与决策过程

用户提出将前端 UI 换装为明日方舟主题。经历三轮意向收敛：

1. 初始提案「罗德岛阵营色卡双主题映射」→ 用户选择先出预览；
2. 罗德岛版预览（黑底亮青）产出后，用户追加 UI 色卡，明确「**主色调用 UI 这套，少量点缀用罗德岛阵营**」；
3. 明日方舟 UI 色卡版预览（深灰面板 + 强调蓝 + 点缀金）产出，用户确认「就这样」定稿。

设计讨论中已确认的取舍：保留现有浅色/深色/跟随系统三态机制不变（`frontend/src/theme.ts` + `.dark` 类切换，既有 `darkModeShortcuts` 单测覆盖）；语义状态色（成功/错误）保留通用色相，仅主色位（`--status-primary-default`）跟随主题主色。

## 2. 最终配色映射

### 主色：明日方舟 UI 色卡

| 色值 | 语义 | 深色主题落位 | 浅色主题落位 |
|---|---|---|---|
| `#2F3132` 深灰面板 | 界面底色/信息面板 | 页面画布（卡片/浮层为 `#383C3E`/`#434749` 亮阶衍生） | 正文/图标深色位、边框 alpha 基色 |
| `#FCFBFB` 纯白 | 文字/图标 | 正文与图标 | 页面画布 |
| `#228EBF` 强调蓝 | 按钮/标签/高亮 | `--bg-brand`/`--primary`/`--ring`（链接文字提亮为 `#45A8D6`） | 同左（链接文字加深为 `#1B7AA6`） |
| `#CBB54C` 点缀金 | 活动/招募等标签 | `--status-warning-default`（深色提亮为 `#D6C268`） | `--status-warning-default` |

### 点缀：罗德岛阵营色卡

| 色值 | 落位 |
|---|---|
| `#3FC6E0` 亮青蓝 | 深色 `--status-primary-default`：分析节点运行态边框 + 辉光；图表系列 `--chart-teal` |
| `#2A5BA8` 罗德岛蓝 | 图表系列 `--chart-violet`（深色提亮 `#7292C9`） |
| `#888A8C` 工业灰 | 两套主题的三级文字/占位符（`--text-tertiary`）与图表网格基色 |
| `#0A0B0D` 罗德岛黑 | 浅色正文（`--text-default`）与浅色反色块（`--bg-invert`） |
| `#F5F5F5` 医疗白 | （间接保留：与 `#FCFBFB` 近似，浅色画布以 UI 色卡为准） |

### 图表系列色策略

冷色系对齐色卡（sky=强调蓝、violet=罗德岛蓝、teal=亮青蓝、amber=点缀金）；coral/mint/rose 三个涨跌语义暖色保持原值，保证多序列曲线可分辨。深色主题仅覆盖 `--chart-sky`/`--chart-violet` 为提亮衍生，补偿深底上对比度。

### 衍生色规则

色卡仅给出主色值，色阶衍生遵循：同色相、只调亮度/透明度；每个衍生值在 `index.css` 令牌注释中标注来源。文字类衍生以 WCAG AA（≥4.5:1）为准绳（如浅色链接 `#1B7AA6` 4.9:1、深色链接 `#45A8D6` ~5.5:1）；按钮底色 `#228EBF` 配白字 3.6:1，与原 UI 色卡「白字蓝底按钮」用法一致，属可接受取舍（大字号/中粗场景）。

## 3. 改动清单

| 文件 | 改动 |
|---|---|
| `frontend/src/index.css` | `:root`/`.dark` 两套令牌全量重映射 + 衍生注释 |
| `frontend/src/test/themePalette.test.ts` | **新增** 调色板冻结测试（4 断言组） |
| `frontend/src/vite-env.d.ts` | **新增** vite client 类型引用（供 `?raw` 导入） |
| `frontend/tailwind.config.js` | brand 三值从硬编码紫改引 `var(--bg-brand*)`（消除令牌双源） |
| `frontend/src/Charts.tsx` | `cssVar` 导出（供 trackRecord 复用）；回退值同步色卡 |
| `frontend/src/pages/trackRecord/*Page.tsx` ×3 | ECharts option 的 antd 硬编码色改 `cssVar()` 取变量 |
| `frontend/src/pages/decisions/DecisionCenter.tsx`、`App.tsx`、trackRecord | 散落 Tailwind 调色板类（text-red-500 等 15 处）改 `text-[color:var(--status-*-default)]` 语义类 |
| `frontend/src/types.ts` | 补 `PredictionRecord.rationale_snapshot?: unknown`（修复 #115 遗留 tsc 构建损坏，已披露） |

附带缺陷修复（已披露）：`TrackRecordPage` 高回撤警示在 `style={{ color: ... }}` 中误用 Tailwind 类名字符串（非法 CSS 值，浏览器忽略导致警示红从未生效），改 `var(--status-error-default)`。

既有测试断言更新 2 处（`decisionCenter.test.tsx`、`trackRecordPage.test.tsx`）：断言目标从旧类名字符串（`'red'`/`'text-red-500'`）改为语义令牌类（`status-error-default`/`status-success-default`）。**断言语义未放宽**（红涨绿跌、高风险红亮均保留），仅实现细节锚点随令牌化迁移——符合「断言被改弱必须能在 diff 中解释原因」红线，原因即本变更的核心意图（类名令牌化）。

## 4. TDD 证据

先写 `themePalette.test.ts` 冻结契约，再应用令牌：

- **红**：`git stash push -- frontend/src/index.css` 恢复旧值后运行 → 4/4 失败（`expected '#4B3FE3' to be '#228EBF'`、`expected '#171717' to be '#2F3132'` 等）；
- **绿**：`git stash pop` 后重跑 → 4/4 通过。

## 5. 验证与门禁

- `npm test`：505/505 通过（vitest 全量，含 darkModeShortcuts 主题机制回归）；
- `npm run build`（tsc -b + vite build）：通过（仅历史 chunk 体积告警）；
- E2E 门禁：**不适用**——`e2e/` 基础设施未落地（project-workflow §3 Step 4.5 生效状态条款），以「全量单测 + 浏览器实测截图 + 用户人工确认」承担，详见 `tests/validation/2026-09-08-update-arknights-ui-theme-validation.md`。

## 6. 执行方式说明

本变更改动集中于单一令牌文件与机械替换，采用单会话直接执行（TDD 纪律不变），未拆分 subagent 流水线与独立计划文件；本文档 §2–§3 即执行蓝图，计划按惯例做完即弃。
