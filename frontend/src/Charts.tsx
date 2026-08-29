import ReactECharts from 'echarts-for-react'
import type { ChartData, AnnualEntry } from './types'

// ── ECharts 主题注入（refactor-ui-design-system Task 5）──
// 每次构建 option 时从 CSS 变量实时读取，保证主题变更后图表跟随；
// getComputedStyle 不可用或变量缺失时回退到原 TRAE Work light 十六进制值。

function cssVar(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

export function getChartTheme() {
  return {
    textColor: cssVar('--muted-foreground', '#525252'),
    axisLabelColor: cssVar('--muted-foreground', '#A3A3A3'),
    tooltipBg: cssVar('--popover', '#FFFFFF'),
    tooltipBorder: cssVar('--border', 'rgba(115, 115, 115, 0.12)'),
    tooltipTextColor: cssVar('--foreground', '#171717'),
    brand: cssVar('--primary', '#4B3FE3'),
    coral: cssVar('--chart-coral', '#F87454'),
    mint: cssVar('--chart-mint', '#1DC981'),
    amber: cssVar('--chart-amber', '#F5A623'),
    sky: cssVar('--chart-sky', '#3B82F6'),
    violet: cssVar('--chart-violet', '#8B5CF6'),
    rose: cssVar('--chart-rose', '#EC4899'),
    teal: cssVar('--chart-teal', '#14B8A6'),
    gridLine: cssVar('--muted-foreground', '#A3A3A3'),
    splitLine: 'rgba(115, 115, 115, 0.08)',
    heat: [
      cssVar('--destructive', '#EF4444'),
      cssVar('--status-warning-default', '#F5A623'),
      cssVar('--status-success-default', '#10B981'),
    ],
  }
}

type ChartTheme = ReturnType<typeof getChartTheme>

// ── Base chart wrapper ──
function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white border rounded-xl p-4" style={{ borderColor: 'var(--border-neutral-l1)' }}>
      <h4 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-default)' }}>{title}</h4>
      {children}
    </div>
  )
}

function baseOption(theme: ChartTheme) {
  return {
    textStyle: { color: theme.textColor, fontSize: 11 },
    tooltip: { trigger: 'axis', backgroundColor: theme.tooltipBg, borderColor: theme.tooltipBorder, textStyle: { color: theme.tooltipTextColor } },
    grid: { left: '8%', right: '8%', bottom: '12%', top: '15%' },
    xAxis: {
      type: 'category' as const,
      axisLabel: { color: theme.axisLabelColor, fontSize: 10 },
      axisLine: { lineStyle: { color: theme.splitLine } },
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: { color: theme.axisLabelColor, fontSize: 10 },
      splitLine: { lineStyle: { color: theme.splitLine } },
    },
  }
}

// ── P0: Revenue & Profit ──
export function RevenueProfitChart({ data }: { data: ChartData }) {
  const annual = data.annual
  if (annual.length < 2) return null
  const years = annual.map(a => a.year)
  const revenue = annual.map(a => a.revenue ?? 0)
  const profit = annual.map(a => a.net_profit ?? 0)
  const theme = getChartTheme()

  const option = {
    ...baseOption(theme),
    legend: { data: ['营业收入', '归母净利润'], bottom: 0, textStyle: { color: theme.textColor, fontSize: 10 } },
    yAxis: [
      { type: 'value', name: '营收(亿)', axisLabel: { color: theme.axisLabelColor }, splitLine: { lineStyle: { color: theme.splitLine } } },
      { type: 'value', name: '利润(亿)', axisLabel: { color: theme.axisLabelColor }, splitLine: { show: false } },
    ],
    series: [
      { name: '营业收入', type: 'bar', data: revenue, itemStyle: { color: theme.brand } },
      { name: '归母净利润', type: 'bar', yAxisIndex: 1, data: profit, itemStyle: { color: theme.coral } },
    ],
  }

  return (
    <ChartCard title="营业收入与归母净利润">
      <ReactECharts option={option} style={{ height: '280px' }} />
    </ChartCard>
  )
}

// ── P0: Growth rates ──
export function GrowthChart({ data }: { data: ChartData }) {
  const g = data.growth
  if (g.years.length < 2) return null

  const theme = getChartTheme()
  const option = {
    ...baseOption(theme),
    legend: { data: ['营收增速', '净利润增速'], bottom: 0, textStyle: { color: theme.textColor, fontSize: 10 } },
    yAxis: { type: 'value', axisLabel: { color: theme.axisLabelColor, formatter: '{value}%' }, splitLine: { lineStyle: { color: theme.splitLine } } },
    series: [
      { name: '营收增速', type: 'line', data: g.revenue_growth, itemStyle: { color: theme.brand }, symbol: 'circle', symbolSize: 6 },
      { name: '净利润增速', type: 'line', data: g.profit_growth, itemStyle: { color: theme.coral }, symbol: 'rect', symbolSize: 6 },
    ],
  }

  return (
    <ChartCard title="同比增速">
      <ReactECharts option={option} style={{ height: '280px' }} />
    </ChartCard>
  )
}

// ── P0: Margins ──
export function MarginChart({ data }: { data: ChartData }) {
  const annual = data.annual
  if (annual.length < 2) return null
  const years = annual.map(a => a.year)
  const gm = annual.map(a => a.gross_margin ?? null)
  const nm = annual.map(a => a.net_margin ?? null)

  const theme = getChartTheme()
  const option = {
    ...baseOption(theme),
    legend: { data: ['毛利率', '净利率'], bottom: 0, textStyle: { color: theme.textColor, fontSize: 10 } },
    yAxis: { type: 'value', axisLabel: { color: theme.axisLabelColor, formatter: '{value}%' }, splitLine: { lineStyle: { color: theme.splitLine } } },
    series: [
      { name: '毛利率', type: 'line', data: gm, smooth: true, itemStyle: { color: theme.mint }, symbol: 'circle', symbolSize: 6 },
      { name: '净利率', type: 'line', data: nm, smooth: true, itemStyle: { color: theme.brand }, symbol: 'circle', symbolSize: 6 },
    ],
  }

  return (
    <ChartCard title="毛利率与净利率">
      <ReactECharts option={option} style={{ height: '280px' }} />
    </ChartCard>
  )
}

// ── P0: ROE ──
export function RoeChart({ data }: { data: ChartData }) {
  const annual = data.annual
  if (annual.length < 2) return null
  const years = annual.map(a => a.year)
  const roe = annual.map(a => a.roe ?? null)

  const theme = getChartTheme()
  const option = {
    ...baseOption(theme),
    yAxis: { type: 'value', axisLabel: { color: theme.axisLabelColor, formatter: '{value}%' }, splitLine: { lineStyle: { color: theme.splitLine } } },
    series: [{
      type: 'line', data: roe, smooth: true,
      itemStyle: { color: theme.amber },
      areaStyle: { opacity: 0.15 },
      symbol: 'circle', symbolSize: 6,
      markLine: {
        // lineStyle 属于 markLine 层级（应用到所有标线）；放进 data 会被 ECharts
        // 当作无坐标的数据点 → 读 coord of undefined → MarkLineView 崩溃
        // "Cannot read properties of undefined (reading 'coord')"，ROE 图渲染失败。
        data: [{ yAxis: 15, label: { formatter: '优秀线 15%', color: theme.axisLabelColor } }],
        lineStyle: { color: theme.gridLine, type: 'dashed' },
      },
    }],
  }

  return (
    <ChartCard title="ROE 变化趋势">
      <ReactECharts option={option} style={{ height: '280px' }} />
    </ChartCard>
  )
}

// ── P0: Cashflow ──
export function CashflowChart({ data }: { data: ChartData }) {
  const annual = data.annual
  if (annual.length < 2) return null
  const years = annual.map(a => a.year)
  const ocf = annual.map(a => a.ocf ?? 0)

  const theme = getChartTheme()
  const option = {
    ...baseOption(theme),
    yAxis: { type: 'value', name: '亿元', axisLabel: { color: theme.axisLabelColor }, splitLine: { lineStyle: { color: theme.splitLine } } },
    series: [{
      type: 'bar', data: ocf,
      itemStyle: { color: (p: any) => p.value >= 0 ? theme.sky : theme.coral },
    }],
  }

  return (
    <ChartCard title="经营现金流净额">
      <ReactECharts option={option} style={{ height: '280px' }} />
    </ChartCard>
  )
}

// ── P1: Stock price ──
export function StockPriceChart({ data }: { data: ChartData }) {
  const daily = data.price.daily
  if (daily.length < 10) return null
  const dates = daily.map(d => d.date)
  const closes = daily.map(d => d.close)
  const earningsDates = data.price.earnings_dates

  const theme = getChartTheme()
  const markLines = earningsDates.map(ed => ({
    xAxis: ed,
    label: { show: false },
    lineStyle: { color: theme.coral, type: 'dashed', opacity: 0.5 },
  }))

  const option = {
    ...baseOption(theme),
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { color: theme.axisLabelColor, fontSize: 9, rotate: 30 },
      axisLine: { lineStyle: { color: theme.splitLine } },
    },
    yAxis: { type: 'value', name: '元', axisLabel: { color: theme.axisLabelColor }, splitLine: { lineStyle: { color: theme.splitLine } } },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 15, bottom: 0 }],
    series: [{
      type: 'line', data: closes,
      itemStyle: { color: theme.brand },
      areaStyle: { opacity: 0.08 },
      symbol: 'none',
      markLine: { data: markLines, symbol: 'none' },
    }],
  }

  return (
    <ChartCard title="股价趋势（红色虚线为年报发布日）">
      <ReactECharts option={option} style={{ height: '300px' }} />
    </ChartCard>
  )
}

// ── P1: Growth vs Price ──
export function GrowthVsPriceChart({ data }: { data: ChartData }) {
  const g = data.growth
  const daily = data.price.daily
  if (g.years.length < 2 || daily.length < 10) return null

  const priceChanges: (number | null)[] = g.years.map(year => {
    const yearPrices = daily.filter(d => d.date.startsWith(year))
    const prevYear = String(parseInt(year) - 1)
    const prevPrices = daily.filter(d => d.date.startsWith(prevYear))
    if (yearPrices.length > 0 && prevPrices.length > 0) {
      return Math.round((yearPrices[yearPrices.length - 1].close - prevPrices[prevPrices.length - 1].close) / prevPrices[prevPrices.length - 1].close * 1000) / 10
    }
    return null
  })

  const theme = getChartTheme()
  const option = {
    ...baseOption(theme),
    legend: { data: ['营收增速', '净利润增速', '股价涨幅'], bottom: 0, textStyle: { color: theme.textColor, fontSize: 10 } },
    yAxis: { type: 'value', axisLabel: { color: theme.axisLabelColor, formatter: '{value}%' }, splitLine: { lineStyle: { color: theme.splitLine } } },
    series: [
      { name: '营收增速', type: 'bar', data: g.revenue_growth, itemStyle: { color: theme.brand } },
      { name: '净利润增速', type: 'bar', data: g.profit_growth, itemStyle: { color: theme.coral } },
      { name: '股价涨幅', type: 'bar', data: priceChanges, itemStyle: { color: theme.mint } },
    ],
  }

  return (
    <ChartCard title="财务增速 vs 股价涨幅">
      <ReactECharts option={option} style={{ height: '280px' }} />
    </ChartCard>
  )
}

// ── P1: Assets & Equity ──
export function AssetsChart({ data }: { data: ChartData }) {
  const annual = data.annual
  if (annual.length < 2) return null
  const years = annual.map(a => a.year)
  const assets = annual.map(a => a.total_assets ?? 0)
  const equity = annual.map(a => a.equity ?? 0)

  const theme = getChartTheme()
  const option = {
    ...baseOption(theme),
    legend: { data: ['总资产', '归母权益'], bottom: 0, textStyle: { color: theme.textColor, fontSize: 10 } },
    yAxis: { type: 'value', name: '亿元', axisLabel: { color: theme.axisLabelColor }, splitLine: { lineStyle: { color: theme.splitLine } } },
    series: [
      { name: '总资产', type: 'bar', data: assets, itemStyle: { color: theme.teal } },
      { name: '归母权益', type: 'bar', data: equity, itemStyle: { color: theme.sky } },
    ],
  }

  return (
    <ChartCard title="总资产与归母权益">
      <ReactECharts option={option} style={{ height: '280px' }} />
    </ChartCard>
  )
}

// ── P1: Contract Liabilities ──
export function ContractLiabChart({ data }: { data: ChartData }) {
  const annual = data.annual
  if (annual.length < 2) return null
  if (annual.every(a => !a.contract_liab)) return null
  const years = annual.map(a => a.year)
  const cl = annual.map(a => a.contract_liab ?? 0)

  const theme = getChartTheme()
  const option = {
    ...baseOption(theme),
    yAxis: { type: 'value', name: '亿元', axisLabel: { color: theme.axisLabelColor }, splitLine: { lineStyle: { color: theme.splitLine } } },
    series: [{ type: 'bar', data: cl, itemStyle: { color: theme.rose } }],
  }

  return (
    <ChartCard title="合同负债">
      <ReactECharts option={option} style={{ height: '280px' }} />
    </ChartCard>
  )
}

// ── P1: Debt Ratio ──
export function DebtRatioChart({ data }: { data: ChartData }) {
  const annual = data.annual
  if (annual.length < 2) return null
  if (annual.every(a => !a.debt_ratio)) return null
  const years = annual.map(a => a.year)
  const dr = annual.map(a => a.debt_ratio ?? null)

  const theme = getChartTheme()
  const option = {
    ...baseOption(theme),
    yAxis: { type: 'value', axisLabel: { color: theme.axisLabelColor, formatter: '{value}%' }, splitLine: { lineStyle: { color: theme.splitLine } } },
    series: [{
      type: 'line', data: dr, smooth: true,
      itemStyle: { color: theme.coral },
      areaStyle: { opacity: 0.10 },
      symbol: 'circle', symbolSize: 6,
    }],
  }

  return (
    <ChartCard title="资产负债率趋势">
      <ReactECharts option={option} style={{ height: '280px' }} />
    </ChartCard>
  )
}

// ── P2: Heatmap ──
export function HeatmapChart({ data }: { data: ChartData }) {
  const daily = data.price.daily
  const earningsDates = data.price.earnings_dates
  if (earningsDates.length < 2 || daily.length < 30) return null

  const windows = [-5, -1, 0, 1, 5, 10, 30]
  const yearLabels: string[] = []
  const heatmapData: [number, number, number][] = []

  earningsDates.forEach((ed, yIdx) => {
    const edDate = new Date(ed)
    const yearLabel = `${edDate.getFullYear()}年报`
    yearLabels.push(yearLabel)
    windows.forEach((offset, xIdx) => {
      const target = new Date(edDate)
      target.setDate(target.getDate() + offset)
      const targetStr = target.toISOString().slice(0, 10)
      let closestIdx = -1
      for (let i = 0; i < daily.length; i++) {
        if (daily[i].date <= targetStr) closestIdx = i
        else break
      }
      let ret = 0
      if (closestIdx > 0) {
        const prev = daily[closestIdx - 1].close
        const curr = daily[closestIdx].close
        if (prev !== 0) ret = Math.round((curr - prev) / prev * 1000) / 10
      }
      heatmapData.push([xIdx, yIdx, ret])
    })
  })

  const theme = getChartTheme()
  const option = {
    tooltip: { position: 'top' },
    grid: { left: '15%', right: '10%', bottom: '15%', top: '10%' },
    xAxis: {
      type: 'category',
      data: windows.map(w => `T${w >= 0 ? '+' : ''}${w}`),
      axisLabel: { color: theme.axisLabelColor, fontSize: 10 },
      splitArea: { show: true },
    },
    yAxis: {
      type: 'category',
      data: yearLabels,
      axisLabel: { color: theme.axisLabelColor, fontSize: 10 },
      splitArea: { show: true },
    },
    visualMap: {
      min: -8, max: 8,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      textStyle: { color: theme.textColor, fontSize: 9 },
      inRange: { color: theme.heat },
    },
    series: [{
      type: 'heatmap',
      data: heatmapData,
      label: { show: true, fontSize: 9, color: '#fff' },
      emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0, 0, 0, 0.3)' } },
    }],
  }

  return (
    <ChartCard title="年报发布窗口期股价变化（%）">
      <ReactECharts option={option} style={{ height: '300px' }} />
    </ChartCard>
  )
}

// ── P2: Market Share ──
export function MarketShareChart({ data }: { data: ChartData }) {
  const ms = data.market_share
  if (!ms || !ms.shares || !Array.isArray(ms.shares)) {
    return (
      <ChartCard title="全球市场份额">
        <div className="flex items-center justify-center h-[200px] text-sm" style={{ color: 'var(--text-tertiary)' }}>
          市场份额数据暂不可得（需额外数据源）
        </div>
      </ChartCard>
    )
  }

  const theme = getChartTheme()
  const option = {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, textStyle: { color: theme.textColor, fontSize: 10 } },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      data: ms.shares.map((s: any) => ({ name: s.name, value: s.value })),
      label: { color: theme.textColor, fontSize: 10 },
      color: [theme.brand, theme.coral, theme.mint, theme.amber, theme.sky, theme.violet, theme.rose, theme.teal],
    }],
  }

  return (
    <ChartCard title="全球市场份额">
      <ReactECharts option={option} style={{ height: '280px' }} />
    </ChartCard>
  )
}

// ── P2: KPI Cards ──
export function KpiCards({ data }: { data: ChartData }) {
  const kpi = data.kpi
  const annual = data.annual
  const latest = annual[0]
  const prev = annual[1]

  const cards: { label: string; value: string; sub?: string }[] = []

  if (kpi.current_price) {
    cards.push({ label: '当前股价', value: `¥${kpi.current_price.toFixed(2)}` })
  }
  if (kpi.pe) {
    cards.push({ label: '市盈率(PE)', value: kpi.pe.toFixed(1) })
  }
  if (kpi.pb) {
    cards.push({ label: '市净率(PB)', value: kpi.pb.toFixed(2) })
  }
  if (kpi.market_cap) {
    cards.push({ label: '总市值', value: `${(kpi.market_cap / 1e8).toFixed(0)}亿` })
  }
  if (latest?.revenue) {
    const growth = prev?.revenue ? ((latest.revenue - prev.revenue) / Math.abs(prev.revenue) * 100).toFixed(1) : null
    cards.push({ label: `${latest.year} 营收`, value: `${latest.revenue.toFixed(1)}亿`, sub: growth ? `同比 ${growth}%` : undefined })
  }
  if (latest?.net_profit) {
    const growth = prev?.net_profit ? ((latest.net_profit - prev.net_profit) / Math.abs(prev.net_profit) * 100).toFixed(1) : null
    cards.push({ label: `${latest.year} 净利润`, value: `${latest.net_profit.toFixed(1)}亿`, sub: growth ? `同比 ${growth}%` : undefined })
  }
  if (latest?.roe) {
    cards.push({ label: `${latest.year} ROE`, value: `${latest.roe.toFixed(1)}%` })
  }
  if (latest?.gross_margin) {
    cards.push({ label: `${latest.year} 毛利率`, value: `${latest.gross_margin.toFixed(1)}%` })
  }
  if (kpi['52w_high']) {
    cards.push({ label: '52周最高', value: `¥${kpi['52w_high'].toFixed(2)}` })
  }
  if (kpi['52w_low']) {
    cards.push({ label: '52周最低', value: `¥${kpi['52w_low'].toFixed(2)}` })
  }

  if (cards.length === 0) return null

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2 mb-4">
      {cards.map((c, i) => (
        <div key={i} className="bg-white border rounded-lg p-3" style={{ borderColor: 'var(--border-neutral-l1)' }}>
          <div className="text-[10px] mb-1" style={{ color: 'var(--text-tertiary)' }}>{c.label}</div>
          <div className="text-base font-bold" style={{ color: 'var(--text-default)', fontFamily: 'var(--font-family-metric)' }}>{c.value}</div>
          {c.sub && <div className="text-[10px] mt-0.5" style={{ color: 'var(--status-success-default)' }}>{c.sub}</div>}
        </div>
      ))}
    </div>
  )
}

// ── Charts Section (all charts in a grid) ──
export function ChartsSection({ data }: { data: ChartData }) {
  if (!data || !data.annual || data.annual.length === 0) return null

  return (
    <div className="space-y-3">
      <KpiCards data={data} />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <RevenueProfitChart data={data} />
        <GrowthChart data={data} />
        <MarginChart data={data} />
        <RoeChart data={data} />
        <CashflowChart data={data} />
        <AssetsChart data={data} />
        <ContractLiabChart data={data} />
        <DebtRatioChart data={data} />
      </div>
      <div className="grid grid-cols-1 gap-3">
        <StockPriceChart data={data} />
        <GrowthVsPriceChart data={data} />
        <HeatmapChart data={data} />
        <MarketShareChart data={data} />
      </div>
    </div>
  )
}