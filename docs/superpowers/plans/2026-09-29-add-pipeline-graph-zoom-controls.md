# Pipeline Graph Zoom Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development

**Goal:** 管线图视图右下角新增「放大 / 缩小 / 重置」控件，步进缩放 + fitView 重置 + 边界禁用。

**Architecture:** `PipelineGraph.tsx` 内新增 `GraphZoomControls` 子组件，作为 `<ReactFlow>` 的 child 渲染（v12 children 位于 Store Provider 内，可直接使用 `useReactFlow`/`useViewport`）；`<Panel position="bottom-right">` 承载三个按钮，样式走应用 CSS 变量，与悬浮详情卡同视觉层级。重置复用初始 `fitViewOptions`（padding 0.15、maxZoom 1）保证「重置 = 回总览」语义一致。

**Tech Stack:** @xyflow/react v12（useReactFlow().zoomIn/zoomOut/fitView；useViewport().zoom 驱动禁用态）、React 18、vitest+RTL（jsdom）、Playwright（timeline 套件 8002/5175）。

## Global Constraints

- 缩放边界沿用组件既有 props：minZoom 0.4 / maxZoom 1.5，不得另设值
- 样式只用 index.css 已定义的 CSS 变量（禁用未定义令牌——2026-09-29 面板透明事故教训）；全量已核对存在：--bg-base-default/--bg-base-secondary/--bg-overlay-l1/--border-neutral-l1/--text-secondary/--text-tertiary/--bg-brand
- selector 全部走 data-testid（graph-zoom-in/out/reset），禁止盲写
- E2E 挂 timeline 套件（pipeline stub 8002/5175），默认 config testIgnore 排除
- 不动双击放大、滚轮平移等既有交互；不修无关的 --text-primary/--bg-primary 遗留问题（另有记录）

---

### Task 1: 单测先行——控件渲染与禁用语义（红）

**Files:**
- Modify: `frontend/src/test/PipelineGraph.test.tsx`

**Interfaces:**
- Produces: 对 `graph-zoom-controls` 容器与 `graph-zoom-in/out/reset` 三按钮的 testid 契约（实现任务按此兑现）

- [ ] **Step 1: Write the failing test**

```tsx
describe('PipelineGraph 缩放控件（add-pipeline-graph-zoom-controls）', () => {
  it('右下角渲染放大/缩小/重置三控件且可点击不抛错', () => {
    render(<PipelineGraph tree={buildLayerTree()} startCounts={{}} onViewDetails={() => {}} />)
    expect(screen.getByTestId('graph-zoom-controls')).toBeDefined()
    expect(screen.getByTestId('graph-zoom-in').getAttribute('aria-label')).toBe('放大')
    expect(screen.getByTestId('graph-zoom-out').getAttribute('aria-label')).toBe('缩小')
    expect(screen.getByTestId('graph-zoom-reset').getAttribute('aria-label')).toBe('重置')
    expect(() => fireEvent.click(screen.getByTestId('graph-zoom-out'))).not.toThrow()
    expect(() => fireEvent.click(screen.getByTestId('graph-zoom-in'))).not.toThrow()
    expect(() => fireEvent.click(screen.getByTestId('graph-zoom-reset'))).not.toThrow()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/test/PipelineGraph.test.tsx`
Expected: FAIL（找不到 graph-zoom-controls）

- [ ] **Step 3: Write minimal implementation**

`PipelineGraph.tsx`：

```tsx
import { Panel, ReactFlow, useReactFlow, useViewport, /* ... */ } from '@xyflow/react'

function GraphZoomControls() {
  const { zoomIn, zoomOut, fitView } = useReactFlow()
  const { zoom } = useViewport()
  const btnStyle = {
    width: 28, height: 28,
    background: 'var(--bg-base-secondary)',
    border: '1px solid var(--border-neutral-l1)',
    color: 'var(--text-secondary)',
  } as const
  return (
    <Panel position="bottom-right" data-testid="graph-zoom-controls" className="!m-3">
      <div className="flex flex-col rounded-lg overflow-hidden" style={{ border: '1px solid var(--border-neutral-l1)' }}>
        <button type="button" data-testid="graph-zoom-in" aria-label="放大" title="放大"
          style={btnStyle} disabled={zoom >= 1.5 - 1e-6}
          onClick={() => zoomIn()}>＋</button>
        <button type="button" data-testid="graph-zoom-out" aria-label="缩小" title="缩小"
          style={btnStyle} disabled={zoom <= 0.4 + 1e-6}
          onClick={() => zoomOut()}>－</button>
        <button type="button" data-testid="graph-zoom-reset" aria-label="重置" title="重置"
          style={btnStyle}
          onClick={() => fitView({ padding: 0.15, maxZoom: 1 })}>⟲</button>
      </div>
    </Panel>
  )
}
```

（实现时以中文语义梳理：步进 ×1.2 / 1÷1.2；重置 fitView 复用初始 options；禁用阈值带浮点容差。图标用 Font Awesome `fa-plus/fa-minus/fa-compress-arrows-alt` 与项目其余图标一致。）

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/test/PipelineGraph.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/PipelineGraph.tsx frontend/src/test/PipelineGraph.test.tsx
git commit -m "feat(frontend): 管线图右下角缩放控件（放大/缩小/重置）"
```

---

### Task 2: E2E——真实浏览器缩放行为（红→绿）

**Files:**
- Create: `tests/e2e/playwright/tests/pipeline-graph-zoom.spec.ts`
- Modify: `tests/e2e/playwright/playwright.timeline.config.ts`（testMatch 挂载）
- Modify: `tests/e2e/playwright/playwright.config.ts`（testIgnore 排除）

**Interfaces:**
- Consumes: Task 1 的 testid 契约；`.react-flow__viewport` 的 transform matrix（缩放读数）

- [ ] **Step 1: Write the failing spec**（导航惯例复用 pipeline-view-toggle.spec.ts：5175 + stub key + 深度模式 + 发送后等 `pipeline-graph` 可见）

断言序列：
1. 三控件可见且位于画布右下（bounding box 右缘/下缘逼近容器右/下缘，容差 24px）
2. 读 `.react-flow__viewport` transform 的 scale s0 → 点「缩小」→ poll scale < s0（1/1.2 步进）
3. 点「放大」→ scale 回升（×1.2）
4. 点「重置」→ poll scale 回到 s0（fitView 总览）
5. 边界禁用：循环点「缩小」至 disabled（poll），再断言「放大」可恢复启用

- [ ] **Step 2: Run to verify red（控件未实现时失败）** → Task 1 已实现后本 spec 应直接绿；红证据 = 控件 testid 缺失

- [ ] **Step 3: scan.sh 自扫 + e2e-reviewer 深审（SDD E2E 门禁嵌入）**

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/playwright/tests/pipeline-graph-zoom.spec.ts tests/e2e/playwright/playwright.timeline.config.ts tests/e2e/playwright/playwright.config.ts
git commit -m "test(e2e): 管线图缩放控件交互回归（timeline 套件）"
```

---

### Task 3: 收口

- [ ] 前端全量单测 + tsc -b
- [ ] 人工验证报告落 `tests/validation/2026-09-29-add-pipeline-graph-zoom-controls-validation.md`
- [ ] tasks.md 全勾 → `openspec validate --strict` → sync 进 `openspec/specs/pipeline-graph-view/spec.md` → archive
