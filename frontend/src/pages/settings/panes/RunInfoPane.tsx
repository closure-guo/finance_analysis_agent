// RunInfoPane 运行信息分区（add-agent-settings-center Task 10）
// 挂载时拉取 GET /api/run-info，纯只读展示后端默认 LLM 配置（model/base_url/thinking）、
// 健康状态、Langfuse 地址与启用态、git 版本/commit；绝不渲染任何密钥字段（契约不含 apiKey）。
import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '../../../components/ui/button'

// 契约：GET /api/run-info（src/finance_agent/api.py）返回以下字段，绝不含 apiKey。
// git_commit 可空：非 git 环境（如 docker 部署，.dockerignore 排除 .git）后端返回 null，
// 不应因该字段为 null 判定整包加载失败（与 base_url 可变缺失同层的降级处理）。
interface RunInfo {
  model: string
  base_url: string
  thinking: string
  langfuse_host: string
  langfuse_enabled: boolean
  version: string
  git_commit: string | null
  health: string
}

// 单项展示行：标签 + 值（值可能较长，允许换行）
function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 py-1.5 text-sm">
      <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <span className="text-right break-all">{value}</span>
    </div>
  )
}

export function RunInfoPane() {
  const [info, setInfo] = useState<RunInfo | null>(null)
  // 加载状态机：loading 首次加载中 / ready 已就绪 / error 首次加载失败（纯只读，无操作触发 refresh）
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  // 拉取运行信息：
  // - mode='full'（初次挂载 / 失败后点重试）：进入 loading，失败置 error 渲染错误态
  // - mode='refresh'：失败保留旧数据、不回落加载态，仅 toast（预留，当前无触发方）
  const loadInfo = useCallback(async (mode: 'full' | 'refresh' = 'full') => {
    if (mode === 'full') setStatus('loading')
    try {
      const res = await fetch('/api/run-info')
      if (!res.ok) throw new Error(String(res.status))
      const data = (await res.json()) as RunInfo
      // 契约校验：仅关键字段（model）缺失才视为加载失败（安全兜底，防止渲染异常形状）；
      // git_commit 可空不判失败——非 git 环境后端返回 null，属合法值。
      if (typeof data.model !== 'string') {
        throw new Error('invalid run-info payload')
      }
      setInfo(data)
      setStatus('ready')
    } catch {
      if (mode === 'full') setStatus('error')
      toast.error('运行信息加载失败')
    }
  }, [])

  useEffect(() => { void loadInfo() }, [loadInfo])

  // 首次加载失败：错误文案 + 重试（点击重新 full 加载）
  if (status === 'error') {
    return (
      <div data-testid="run-info-error" className="py-6 text-sm space-y-3" style={{ color: 'var(--text-tertiary)' }}>
        <p>运行信息加载失败</p>
        <Button data-testid="run-info-retry" size="sm" variant="outline" onClick={() => void loadInfo()}>
          重试
        </Button>
      </div>
    )
  }

  if (status === 'loading' || !info) {
    return <div className="py-6 text-sm" style={{ color: 'var(--text-tertiary)' }}>运行信息加载中…</div>
  }

  return (
    <div data-testid="run-info-pane" className="space-y-6">
      {/* 运行环境与版本 */}
      <div className="rounded-xl p-4 space-y-1" style={{ background: 'var(--bg-overlay-l1)' }}>
        <h3 className="text-sm font-medium mb-2">运行环境</h3>
        <InfoRow label="模型" value={info.model} />
        <InfoRow label="API 地址" value={info.base_url || '—'} />
        <InfoRow label="思考模式" value={info.thinking || '—'} />
        <InfoRow label="健康状态" value={info.health === 'ok' ? '正常' : (info.health || '—')} />
      </div>

      {/* 可观测性：Langfuse */}
      <div className="rounded-xl p-4 space-y-1" style={{ background: 'var(--bg-overlay-l1)' }}>
        <h3 className="text-sm font-medium mb-2">可观测性（Langfuse）</h3>
        <InfoRow label="地址" value={info.langfuse_host || '—'} />
        <InfoRow label="链路追踪" value={info.langfuse_enabled ? '已启用' : '未启用'} />
      </div>

      {/* 版本信息 */}
      <div className="rounded-xl p-4 space-y-1" style={{ background: 'var(--bg-overlay-l1)' }}>
        <h3 className="text-sm font-medium mb-2">版本信息</h3>
        <InfoRow label="版本" value={info.version || '—'} />
        <InfoRow label="Git Commit" value={info.git_commit || '—'} />
      </div>
    </div>
  )
}
