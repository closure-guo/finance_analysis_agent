// SessionsPane 会话管理分区（add-agent-settings-center Task 9）
// stub fetch 按 URL 分发，仿 cachePane.test.tsx / trackRecordPage.test.tsx 范式
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { SessionsPane } from '../../pages/settings/panes/SessionsPane'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    if (url.endsWith('/api/sessions')) return Promise.resolve(new Response(JSON.stringify([{}, {}, {}])))
    if (url.endsWith('/api/sessions/clear-all')) return Promise.resolve(new Response(JSON.stringify({ cleared: 3 })))
    return Promise.resolve(new Response('{}'))
  }))
})
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('SessionsPane 会话管理分区', () => {
  it('展示会话总数并二次确认后清空', async () => {
    const onCleared = vi.fn()
    render(<SessionsPane onCleared={onCleared} />)
    expect(await screen.findByText('3')).toBeInTheDocument()
    fireEvent.click(screen.getByText('清空全部会话'))
    expect(screen.getByText(/确认/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('确认清空'))
    await waitFor(() => expect(onCleared).toHaveBeenCalled())
  })
})
