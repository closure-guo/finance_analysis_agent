# refactor-ui-design-system Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 shadcn/ui 设计令牌与组件原语，把手写通用控件替换为 shadcn 原语，图表配色对齐主题——只改视觉不改行为。

**Architecture:** 渐进共存：在现有 Tailwind（TRAE Work 令牌）之上叠加 shadcn 语义令牌层（`--background/--foreground/--muted/--primary/--border/--radius` 等，值映射自现有 TRAE 调色板，保持现有视觉风格）；`components/ui/` 收录 shadcn 原语源码；逐个替换手写控件；Charts.tsx 从 CSS 变量取色注入 ECharts option。

**Tech Stack:** Tailwind CSS 3.4（已装）、shadcn/ui（radix 源码入仓）、class-variance-authority、clsx、tailwind-merge、sonner、lucide-react、ECharts 6（保留）。

## Global Constraints

- 现有前端测试 SHALL **无修改**通过（`cd frontend && npm test`）——行为不变的硬约束（spec 锁定）
- 不得改变交互行为、路由结构、API 契约、SSE 事件语义
- 不拆分 App.tsx 逻辑架构；不接 assistant-ui；不做暗色切换入口（仅预留变量）
- 重构组件内不得出现十六进制色值（Charts.tsx 除外，改从 CSS 变量取值）
- 替换控件时保留全部既有 `data-testid` 属性
- 提交信息用中文描述，格式 `feat(frontend): ...`
- OpenSpec change：`openspec/changes/refactor-ui-design-system/`（校验已通过）

## 现状事实（勘察结论，2026-08-29）

- Tailwind 3.4 已安装配置：`frontend/tailwind.config.js`（TRAE 语义令牌）、`postcss.config.js`、`index.css` 以 `@tailwind` 指令开头
- 全局样式在 `frontend/src/index.css`（TRAE Work Light 主题变量 `--bg-base-default` 等）
- 十六进制色值仅存在于 `frontend/src/Charts.tsx`（`_textColor='#525252'`、`brand:'#4B3FE3'` 等，grep 已确认全仓唯一）
- 手写控件分布：`App.tsx`（SessionItem 删除按钮、EmptyState 模式/配置下拉、header 按钮输入区、SettingsModal 由 `showSettings` 控制）+ `ReportFileDrawer.tsx`（下载按钮）+ `SearchBanner.tsx`
- 无 toast 库、无 react-router；测试入口 `cd frontend && npm test`（vitest + testing-library，setup 在 `src/test/setup.ts`）
- E2E 门禁命令：`cd tests/e2e/playwright && npx playwright test`（默认 config，baseURL 5173）

---

### Task 1: shadcn 语义令牌层打底

**Files:**
- Modify: `frontend/src/index.css`（`:root` 变量块末尾追加）
- Modify: `frontend/tailwind.config.js`（theme.extend.colors 与 borderRadius）

**Interfaces:**
- Produces: Tailwind 语义类 `bg-background text-foreground bg-muted text-muted-foreground bg-primary text-primary-foreground bg-secondary bg-accent border-border ring-ring text-destructive`、`rounded-[var(--radius)]`；后续所有 UI 原语与页面重构依赖这批类名。

- [ ] **Step 1: 在 `index.css` 的 `:root` 内追加 shadcn 令牌（值映射自现有 TRAE 调色板，保持视觉不变）**

```css
  /* ── shadcn semantic tokens（refactor-ui-design-system）：映射 TRAE 调色板 ── */
  --background: #FFFFFF;
  --foreground: #171717;
  --card: #FFFFFF;
  --card-foreground: #171717;
  --popover: #FFFFFF;
  --popover-foreground: #171717;
  --primary: #4B3FE3;
  --primary-foreground: #FFFFFF;
  --secondary: #FAFAFA;
  --secondary-foreground: #525252;
  --muted: #F5F5F5;
  --muted-foreground: #A3A3A3;
  --accent: #EFEFEF;
  --accent-foreground: #171717;
  --destructive: #EF4444;
  --destructive-foreground: #FFFFFF;
  --border: rgba(115, 115, 115, 0.12);
  --input: rgba(115, 115, 115, 0.20);
  --ring: #4B3FE3;
  --radius: 8px;
```

- [ ] **Step 2: `tailwind.config.js` 的 `theme.extend` 增加**

```js
      colors: {
        // …既有 TRAE 令牌保持不动…
        background: 'var(--background)',
        foreground: 'var(--foreground)',
        card: { DEFAULT: 'var(--card)', foreground: 'var(--card-foreground)' },
        popover: { DEFAULT: 'var(--popover)', foreground: 'var(--popover-foreground)' },
        primary: { DEFAULT: 'var(--primary)', foreground: 'var(--primary-foreground)' },
        secondary: { DEFAULT: 'var(--secondary)', foreground: 'var(--secondary-foreground)' },
        muted: { DEFAULT: 'var(--muted)', foreground: 'var(--muted-foreground)' },
        accent: { DEFAULT: 'var(--accent)', foreground: 'var(--accent-foreground)' },
        destructive: { DEFAULT: 'var(--destructive)', foreground: 'var(--destructive-foreground)' },
        border: 'var(--border)',
        input: 'var(--input)',
        ring: 'var(--ring)',
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
```

- [ ] **Step 3: 验证无回归**

Run: `cd frontend && npm test` → 既有用例全绿（无修改）。

- [ ] **Step 4: Commit** `git add frontend/src/index.css frontend/tailwind.config.js && git commit -m "feat(frontend): shadcn 语义令牌层打底（refactor-ui-design-system 1.1/1.3）"`

### Task 2: 重构前视觉基线截图

**Files:**
- Create: `tests/e2e/playwright/tests/visual-baseline.spec.ts`（一次性采集工具，不进常规门禁断言）
- Create: `tests/validation/ui-baseline/`（截图产物目录，git 跟踪）

- [ ] **Step 1: 写采集 spec**——访问 `http://localhost:5173/`（空态页）、点击设置齿轮截设置弹窗，`page.screenshot({ fullPage: true })` 写入 `tests/validation/ui-baseline/`（`empty-state.png`、`settings-modal.png`）；用 `process.env.BASELINE_DIR` 控制输出目录，默认跳过（`test.skip(!process.env.BASELINE_DIR)`），避免污染日常门禁。
- [ ] **Step 2: 启动前后端**（docker compose 或本地 uvicorn + vite），执行 `BASELINE_DIR=../../validation/ui-baseline npx playwright test visual-baseline.spec.ts`，确认两张基线图落盘。
- [ ] **Step 3: Commit** 截图与 spec。

### Task 3: cn 工具 + shadcn 原语入仓

**Files:**
- Create: `frontend/src/lib/utils.ts`（`cn()`）
- Create: `frontend/src/components/ui/button.tsx`、`input.tsx`、`textarea.tsx`、`dialog.tsx`、`tooltip.tsx`、`dropdown-menu.tsx`、`sonner.tsx`

**Interfaces:**
- Produces: `cn(...inputs: ClassValue[])`；`Button`（variants: default/secondary/ghost/destructive/outline；sizes: default/sm/icon；`asChild` 支持）、`Input`、`Textarea`、`Dialog/DialogContent/DialogHeader/DialogTitle/DialogDescription/DialogFooter/DialogClose`、`TooltipProvider/Tooltip/TooltipTrigger/TooltipContent`、`DropdownMenu` 全家、`Toaster`（sonner 封装，`position="top-center"`）。Task 4/5 按这些名字消费。

- [ ] **Step 1: 安装依赖**（版本取当前 stable，React 18 兼容）

```bash
cd frontend && npm install class-variance-authority clsx tailwind-merge sonner lucide-react @radix-ui/react-dialog @radix-ui/react-tooltip @radix-ui/react-dropdown-menu
```

- [ ] **Step 2: 写入 `lib/utils.ts` 与 `components/ui/*`**——按 shadcn/ui 官方源码（new-york 风格）收录，样式类改用 Task 1 语义令牌（如 `bg-primary text-primary-foreground hover:bg-primary/90`、`border-input`）；sonner.tsx 用 `next-themes`-free 版本，直接 `<Toaster className="toaster group" style={{ '--normal-bg': 'var(--popover)', ... }} />`。
- [ ] **Step 3: 在 `App.tsx` 根部挂 `<Toaster />`（仅挂载，暂无调用方）**
- [ ] **Step 4: 验证** `npm test` 全绿 + `npm run build` 通过；Commit `feat(frontend): shadcn 原语入仓（button/input/textarea/dialog/tooltip/dropdown/sonner）`

### Task 4: 手写控件替换（行为不变）

**Files:**
- Modify: `frontend/src/App.tsx`（SessionItem 删除按钮、EmptyState 输入区/下拉、header 按钮、SettingsModal 打开/关闭容器、输入 textarea）
- Modify: `frontend/src/ReportFileDrawer.tsx`、`frontend/src/SearchBanner.tsx`（按钮/输入替换）

**Interfaces:**
- Consumes: Task 3 全部原语。
- 约束：所有 `data-testid` 原样保留；受控组件 value/onChange 逻辑不动；下拉展开/收起行为（含 useClickOutside 语义）由 DropdownMenu 原语承担，`dropdownOutsideClick.test.tsx` 与 `useClickOutside.test.tsx` 无修改通过是验收线。

- [ ] **Step 1: SettingsModal 外层改为受控 `Dialog`**（open/onOpenChange 绑定 `showSettings/setShowSettings`），内部表单控件换 `Input/Textarea`，底部按钮换 `Button`；Esc/遮罩关闭行为由 Dialog 原生提供（与现状一致）。
- [ ] **Step 2: EmptyState 与设置内的模式/配置下拉换 `DropdownMenu`**；保留原 aria 文案与选中态样式（选中项 `bg-accent`）。
- [ ] **Step 3: 各处按钮换 `Button`**（图标钮用 `variant="ghost" size="icon"`；主行动钮 `variant="default"`；危险钮 `variant="destructive"`）；输入框换 `Input/Textarea`。
- [ ] **Step 4: 每替换一处删除对应旧 CSS**（`index.css` 中 `.glass-card`/`.glass-input`/`.chip` 等若无引用则删）。
- [ ] **Step 5: 验证** `npm test` 全绿（禁止修改任何既有测试文件）；`npm run build` 通过；Commit。

### Task 5: ECharts 主题注入 + 色值清查

**Files:**
- Modify: `frontend/src/Charts.tsx`

**Interfaces:**
- Produces: 模块级函数 `getChartTheme(): { textColor, axisLabelColor, tooltipBg, tooltipTextColor, brand, coral, mint, amber, sky, violet, rose, teal, gridLine }`——从 `getComputedStyle(document.documentElement).getPropertyValue(...)` 读取（读取点：每个 option 构建函数入口，保证响应主题变化；缺失时回退现值）。

- [ ] **Step 1: 定义 `getChartTheme`**：`--foreground`→tooltipTextColor、`--muted-foreground`→textColor/axisLabelColor、`--popover`→tooltipBg、`--primary`→brand、其余系列色（coral/mint/amber/sky/violet/rose/teal）新增 CSS 变量 `--chart-coral` 等到 `index.css`（值 = 现十六进制），option 全部改从 theme 对象取值。
- [ ] **Step 2: 交叉线/visualMap 等散落色值同样替换**（`#A3A3A3`→`gridLine`，`['#EF4444','#F5A623','#10B981']`→`['var(--destructive)', 'var(--status-warning-default)', 'var(--status-success-default)']` 的 computed 读取值——在 theme 对象中新增 `heat: [r,g,b]` 三元组取自现有 `--status-*` 变量）。
- [ ] **Step 3: 验证** `npm test`（`chartsMarkLine.test.tsx` 等无修改通过；getComputedStyle 在 jsdom 返回空串 → 回退默认值路径被自然覆盖）；grep 全仓 `#[0-9a-fA-F]{6}` 仅剩 `index.css` 与 `tailwind.config.js`；Commit。

### Task 6: 验证与门禁

- [ ] **Step 1:** `cd frontend && npm test` 全绿（零测试修改）；`npm run build` 通过。
- [ ] **Step 2:** E2E 门禁 `cd tests/e2e/playwright && npx playwright test` 全绿。
- [ ] **Step 3:** 重跑 Task 2 采集脚本输出重构后截图至 `tests/validation/ui-after/`，与基线逐页对比（人工/判图），确认仅风格变化无布局破损；结论写入 `tests/validation/2026-08-29-refactor-ui-design-system-validation.md`。
- [ ] **Step 4:** 勾选 `openspec/changes/refactor-ui-design-system/tasks.md`；archive 等人工验证签字后走 openspec-archive-change。
