// RunInfoPane 运行信息分区（add-agent-settings-center Task 10）
// stub fetch 按 URL 分发并记录调用，仿 sessionsPane.test.tsx / cachePane.test.tsx 范式。
// 契约对齐 GET /api/run-info（src/finance_agent/api.py）：
// { model, base_url, thinking, langfuse_host, langfuse_enabled, version, git_commit, health }
// 响应绝不含 apiKey 等密钥字段。
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { RunInfoPane } from '../../pages/settings/panes/RunInfoPane'

// 记录全部 fetch 调用。通过全局 __runInfoFail 让第 N 次 /api/run-info 请求返回 500（0/缺省 = 永不失败）；
// __runInfoGitCommit 定制 git_commit 返回值（null 模拟非 git 环境，如 docker 部署）。
function stubFetch(calls: Array<{ url: string; init?: RequestInit }>) {
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    calls.push({ url, init })
    if (url.endsWith('/api/run-info')) {
      const failAt = (globalThis as unknown as { __runInfoFail?: number }).__runInfoFail ?? 0
      const runInfoCalls = calls.filter(c => c.url === '/api/run-info').length
      if (failAt > 0 && runInfoCalls === failAt) {
        return Promise.resolve(new Response(JSON.stringify({ error: 'boom' }), { status: 500 }))
      }
      // 契约：GET /api/run-info 只读返回运行信息，绝不含 apiKey；git_commit 后端声明为 string|null。
      // 注意：此处不能对 __runInfoGitCommit 用 ?? 做缺省回退——null 是合法的“非 git 环境”契约值，
      // 而 ?? 会把 null 当作未设置直接吞掉；应由 beforeEach 提供默认 'abc123' 后原样透传。
      const gitCommit = (globalThis as unknown as { __runInfoGitCommit: string | null }).__runInfoGitCommit
      return Promise.resolve(new Response(JSON.stringify({
        model: 'deepseek/deepseek-chat',
        base_url: 'https://api.deepseek.com/v1',
        thinking: 'enabled',
        langfuse_host: 'http://localhost:3000',
        langfuse_enabled: true,
        version: '0.1.0',
        git_commit: gitCommit,
        health: 'ok',
      })))
    }
    return Promise.resolve(new Response('{}'))
  }))
}

describe('RunInfoPane 运行信息分区', () => {
  beforeEach(() => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    stubFetch(calls)
    ;(globalThis as unknown as { __calls?: Array<{ url: string; init?: RequestInit }> }).__calls = calls
    ;(globalThis as unknown as { __runInfoFail?: number }).__runInfoFail = 0
    ;(globalThis as unknown as { __runInfoGitCommit: string | null }).__runInfoGitCommit = 'abc123'
  })
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

  it('挂载即拉取 /api/run-info 并只读展示各字段', async () => {
    render(<RunInfoPane />)
    expect(await screen.findByText(/deepseek\/deepseek-chat/)).toBeInTheDocument()
    expect(screen.getByText(/https:\/\/api\.deepseek\.com\/v1/)).toBeInTheDocument()
    expect(screen.getByText(/enabled/)).toBeInTheDocument()
    expect(screen.getByText(/http:\/\/localhost:3000/)).toBeInTheDocument()
    expect(screen.getByText(/abc123/)).toBeInTheDocument()
    expect(screen.getByText(/0\.1\.0/)).toBeInTheDocument()
    // 健康状态以「正常」中文展示
    expect(screen.getByText('正常')).toBeInTheDocument()
    // Langfuse 启用态
    expect(screen.getByText('已启用')).toBeInTheDocument()
    // 仅发起一次 run-info 请求
    const calls = (globalThis as unknown as { __calls: Array<{ url: string }> }).__calls
    expect(calls.filter(c => c.url === '/api/run-info')).toHaveLength(1)
  })

  it('绝不渲染任何密钥字段', async () => {
    render(<RunInfoPane />)
    await screen.findByText(/deepseek\/deepseek-chat/)
    // apiKey / secret 等敏感关键词不应出现在页面上
    expect(screen.queryByText(/apiKey/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/secret/i)).not.toBeInTheDocument()
    // 仅展示契约声明的 8 个字段，无额外密钥条目
    expect(screen.queryByText(/密钥/)).not.toBeInTheDocument()
  })

  it('git_commit 为 null（非 git 环境）时分区正常展示，Git Commit 渲染 —，不进入错误态', async () => {
    // 模拟 docker 部署：后端 _git_commit() 返回 None → JSON 中 git_commit: null
    ;(globalThis as unknown as { __runInfoGitCommit: null }).__runInfoGitCommit = null
    render(<RunInfoPane />)
    // 其余字段照常展示，不进错误态
    expect(await screen.findByText(/deepseek\/deepseek-chat/)).toBeInTheDocument()
    expect(screen.getByText(/https:\/\/api\.deepseek\.com\/v1/)).toBeInTheDocument()
    expect(screen.getByText(/enabled/)).toBeInTheDocument()
    expect(screen.getByText(/http:\/\/localhost:3000/)).toBeInTheDocument()
    expect(screen.getByText(/0\.1\.0/)).toBeInTheDocument()
    expect(screen.getByText('正常')).toBeInTheDocument()
    // git_commit 以 — 兜底，不再渲染字面 hash 或 'undefined'
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.queryByText(/abc123/)).not.toBeInTheDocument()
    expect(screen.queryByText(/undefined/)).not.toBeInTheDocument()
    // 不进入错误态
    expect(screen.queryByTestId('run-info-error')).not.toBeInTheDocument()
    expect(screen.queryByText('运行信息加载失败')).not.toBeInTheDocument()
  })

  it('首次加载失败进入错误态，点重试后恢复展示', async () => {
    // 第 1 次失败，第 2 次成功
    ;(globalThis as unknown as { __runInfoFail: number }).__runInfoFail = 1
    render(<RunInfoPane />)
    expect(await screen.findByTestId('run-info-error')).toBeInTheDocument()
    expect(screen.getByText('运行信息加载失败')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('run-info-retry'))
    expect(await screen.findByText(/deepseek\/deepseek-chat/)).toBeInTheDocument()
    const calls = (globalThis as unknown as { __calls: Array<{ url: string }> }).__calls
    expect(calls.filter(c => c.url === '/api/run-info')).toHaveLength(2)
  })

  it('首次加载期间显示加载中占位', () => {
    render(<RunInfoPane />)
    expect(screen.getByText('运行信息加载中…')).toBeInTheDocument()
  })
})
