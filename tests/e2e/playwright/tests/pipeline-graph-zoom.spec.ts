import { test, expect } from '@playwright/test'

/**
 * 管线图缩放控件 E2E（add-pipeline-graph-zoom-controls）
 *
 * 覆盖 delta spec 三场景：缩小/放大步进、重置回总览、缩放边界禁用。
 * 缩放读数取 React Flow 视口 `.react-flow__viewport` 的内联 transform scale
 * （React Flow 渲染契约）；selector 全部来自已提交前端源码：
 * - pipeline-graph：App.tsx 图视图容器
 * - graph-zoom-in / graph-zoom-out / graph-zoom-reset / graph-zoom-controls：PipelineGraph.tsx
 *
 * 环境与确定性方案（STUB_SCENARIO=pipeline，后端 8002 / 前端 5175，
 * playwright.timeline.config.ts 拉起）：与 persist-full-session-timeline.spec.ts 相同——
 * 经 /api/test/seed 真实写入 session_store（不 mock 业务接口），造一个 status=completed
 * 的 analysis 会话后从侧边栏打开。完成态管线卡静态渲染图视图，规避实时流式重渲染
 * 造成的元素重挂竞态（实时运行中交互属另一场景，由人工验证覆盖）。
 */

const API_BASE = 'http://localhost:8002'
const FRONTEND_BASE = 'http://localhost:5175'

test.setTimeout(120_000)

async function readScale(page: import('@playwright/test').Page): Promise<number> {
  // JUSTIFIED: React Flow 视口缩放无用户态定位器/角色可断言，transform scale 是其渲染契约；
  // 元素交互全部走 getByTestId，此处仅测量
  const t = await page.evaluate(() => {
    const vp = document.querySelector<HTMLElement>('.react-flow__viewport')
    return vp ? vp.style.transform : ''
  })
  const m = t.match(/scale\(([\d.]+)\)/)
  if (!m) throw new Error(`viewport transform 未就绪: "${t}"`)
  return Number(m[1])
}

test.describe('管线图缩放控件', () => {
  test('右下角控件可缩小/放大步进、重置回总览、边界禁用', async ({ page }) => {
    // 造完成态 analysis 会话：层树结构与 pipelineTree.LAYER_TREE_CONFIG 一致
    //（层含 children{nodeId,label,status}，图视图 DAG 节点画的是层的 children）
    const layerTree = [
      { id: 'prep', label: 'PREP', status: 'completed', children: [
        { nodeId: 'check_cache', label: '数据准备', status: 'completed' },
        { nodeId: 'fetch_data', label: '获取数据', status: 'completed' },
        { nodeId: 'validate_financials', label: '勾稽校验', status: 'completed' },
        { nodeId: 'compute_metrics', label: '指标计算', status: 'completed' },
        { nodeId: 'verify_citations', label: '引用校验', status: 'completed' },
      ] },
      { id: 'layer1', label: 'Layer I', status: 'completed', children: [
        { nodeId: 'fundamental_analyst', label: '基本面', status: 'completed' },
        { nodeId: 'technical_analyst', label: '技术面', status: 'completed' },
        { nodeId: 'macro_analyst', label: '宏观', status: 'completed' },
        { nodeId: 'sentiment_analyst', label: '舆情', status: 'completed' },
      ] },
      { id: 'layer2', label: 'Layer II', status: 'completed', children: [
        { nodeId: 'bull_r1', label: '看多 R1', status: 'completed' },
        { nodeId: 'bear_r1', label: '看空 R1', status: 'completed' },
        { nodeId: 'bull_r2', label: '看多 R2', status: 'completed' },
        { nodeId: 'bear_r2', label: '看空 R2', status: 'completed' },
        { nodeId: 'research_manager', label: '研究结论', status: 'completed' },
      ] },
      { id: 'trader', label: 'Trader', status: 'completed', children: [
        { nodeId: 'trader', label: '交易决策', status: 'completed' },
      ] },
      { id: 'risk', label: 'Risk', status: 'completed', children: [
        { nodeId: 'aggressive_r1', label: '激进风控 R1', status: 'completed' },
        { nodeId: 'conservative_r1', label: '保守风控 R1', status: 'completed' },
        { nodeId: 'neutral_r1', label: '中性风控 R1', status: 'completed' },
        { nodeId: 'aggressive_r2', label: '激进风控 R2', status: 'completed' },
        { nodeId: 'conservative_r2', label: '保守风控 R2', status: 'completed' },
        { nodeId: 'neutral_r2', label: '中性风控 R2', status: 'completed' },
        { nodeId: 'risk_judge', label: '风控裁决', status: 'completed' },
      ] },
      { id: 'fund', label: 'Fund', status: 'completed', children: [
        { nodeId: 'fund_manager', label: '基金经理', status: 'completed' },
        { nodeId: 'generate_report', label: '报告生成', status: 'completed' },
        { nodeId: 'generate_file', label: '文件导出', status: 'completed' },
      ] },
    ]
    const seedResp = await page.request.post(`${API_BASE}/api/test/seed`, {
      data: {
        display_name: 'E2E管线缩放控件会话',
        session_type: 'analysis',
        status: 'completed',
        report_markdown: '# 贵州茅台深度分析报告\n\n结论：谨慎增持。',
        chat_history: [{ role: 'user', content: '深度分析600519' }],
        pipeline_snapshot: {
          layerTree: JSON.stringify(layerTree),
          currentNodeId: '',
          progress: 1,
          updatedAt: 1700000000000,
        },
      },
    })
    expect(seedResp.ok()).toBeTruthy()

    await page.goto(FRONTEND_BASE)
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'stub-key-for-testing')
      localStorage.setItem('fa_user_id', 'user-graph-zoom')
      // 不设 fa_pipeline_view → 默认 graph 视图
      localStorage.removeItem('fa_pipeline_view')
    })
    await page.reload()

    // 打开完成态会话：管线卡默认折叠为完成摘要条，点击展开后图视图静态渲染
    // （无流式重挂）；节点 id 与 graphModel/buildLayerTree 一致
    // JUSTIFIED: 复跑时侧边栏可能存在同名旧会话，first 锁定最新一条（persist-full-session-timeline 同惯例）
    await page.getByText('E2E管线缩放控件会话', { exact: true }).first().click()

    const summaryBar = page.getByTestId('pipeline-summary')
    await expect(summaryBar).toBeVisible({ timeout: 15_000 })
    await summaryBar.click()

    const graph = page.getByTestId('pipeline-graph')
    await expect(graph).toBeVisible({ timeout: 15_000 })
    // 种子必须过渲染守卫：DAG 节点真实可见（防空画布假通过——缩放断言对空图同样成立）
    await expect(page.getByTestId('graph-node-fundamental_analyst')).toBeVisible({ timeout: 15_000 })

    // 控件渲染于画布右下角：控件盒右缘/下缘逼近容器右缘/下缘（容差 40px）
    const controls = page.getByTestId('graph-zoom-controls')
    await expect(controls).toBeVisible()
    const graphBox = await graph.boundingBox()
    const controlsBox = await controls.boundingBox()
    expect(graphBox).not.toBeNull()
    expect(controlsBox).not.toBeNull()
    if (graphBox && controlsBox) {
      expect(controlsBox.x + controlsBox.width).toBeGreaterThan(graphBox.x + graphBox.width - 40)
      expect(controlsBox.y + controlsBox.height).toBeGreaterThan(graphBox.y + graphBox.height - 40)
    }

    // 缩放步进：fitView 后 s0 ≤ maxZoom 1 < 1.5，「放大」恒可用且树宽无关（真实宽 DAG
    // 下 fitView 可能已钳在 minZoom，「缩小」初始可禁用，故先放大）；
    // 放大 ×1.2 → 缩小 1/1.2 回到 s0 → 重置回总览 s0
    const s0 = await readScale(page)
    await page.getByTestId('graph-zoom-in').click()
    await expect
      .poll(() => readScale(page), { timeout: 5_000 })
      .toBeGreaterThan(s0)
    const s1 = await readScale(page)
    await page.getByTestId('graph-zoom-out').click()
    await expect
      .poll(async () => Math.abs((await readScale(page)) - s0), { timeout: 5_000 })
      .toBeLessThan(1e-6)
    expect(s1).toBeCloseTo(s0 * 1.2, 6)
    await page.getByTestId('graph-zoom-reset').click()
    await expect
      .poll(async () => Math.abs((await readScale(page)) - s0), { timeout: 5_000 })
      .toBeLessThan(1e-6)

    // 边界禁用：连续缩小至 minZoom 后「缩小」禁用、「放大」仍可用
    await expect
      .poll(async () => {
        const disabled = await page.getByTestId('graph-zoom-out').isDisabled()
        if (!disabled) await page.getByTestId('graph-zoom-out').click()
        return disabled
      }, { timeout: 15_000 })
      .toBe(true)
    await expect(page.getByTestId('graph-zoom-in')).toBeEnabled()
  })
})
