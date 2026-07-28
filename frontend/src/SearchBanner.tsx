import { useState } from 'react'

// 搜索结果条目
interface SearchResult {
  title: string
  url: string
  content: string
}

// SearchBanner 组件支持三态：搜索中 / 完成 / 失败
// embedded=true 时嵌入 TimelineRenderer 统一白色容器：去掉自身灰底框与外边距，融入时间轴。
interface SearchBannerProps {
  status: 'searching' | 'done' | 'error'
  query?: string
  results?: SearchResult[]
  embedded?: boolean
}

// 从 URL 提取域名
function getDomain(url: string): string {
  try {
    return new URL(url).hostname.replace('www.', '')
  } catch {
    return url
  }
}

// 从 URL 生成 favicon 地址
function getFavicon(url: string): string {
  try {
    const domain = new URL(url).hostname
    return `https://www.google.com/s2/favicons?domain=${domain}&sz=32`
  } catch {
    return ''
  }
}

export function SearchBanner({ status, query, results = [], embedded = false }: SearchBannerProps) {
  const [expanded, setExpanded] = useState(false)

  // 搜索中：脉冲动画 + "正在搜索：{query}"
  if (status === 'searching') {
    return (
      <div className={embedded ? '' : 'mb-3'}>
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg" style={{ background: embedded ? 'transparent' : 'var(--bg-overlay-l1)' }}>
          <span className="relative flex h-2 w-2 flex-shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: 'var(--bg-brand)' }}></span>
            <span className="relative inline-flex rounded-full h-2 w-2" style={{ background: 'var(--bg-brand)' }}></span>
          </span>
          <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            正在搜索
            {query && <span className="ml-1.5" style={{ color: 'var(--text-tertiary)' }}>：{query}</span>}
          </span>
        </div>
      </div>
    )
  }

  // 搜索失败
  if (status === 'error') {
    return (
      <div className={embedded ? '' : 'mb-3'}>
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg" style={{ background: embedded ? 'transparent' : 'var(--bg-overlay-l1)' }}>
          <i className="fas fa-exclamation-circle text-xs flex-shrink-0" style={{ color: 'var(--status-error-default)' }}></i>
          <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>搜索失败</span>
        </div>
      </div>
    )
  }

  // 搜索完成：可折叠的结果列表
  return (
    <div className={embedded ? '' : 'mb-3'}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-left"
        style={{ background: embedded ? 'transparent' : 'var(--bg-overlay-l1)' }}
        onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--bg-overlay-l2)' }}
        onMouseLeave={(e) => { e.currentTarget.style.background = embedded ? 'transparent' : 'var(--bg-overlay-l1)' }}
      >
        <i className="fas fa-search text-xs flex-shrink-0" style={{ color: 'var(--status-success-default)' }}></i>
        <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
          搜索了
          <span className="mx-1 font-medium" style={{ color: 'var(--text-default)' }}>{results.length}</span>
          个网页
          {query && <span className="ml-1.5" style={{ color: 'var(--text-tertiary)' }}>· {query}</span>}
        </span>
        <i className={`fas fa-chevron-${expanded ? 'down' : 'right'} text-[10px] ml-auto transition-transform`} style={{ color: 'var(--text-tertiary)' }}></i>
      </button>
      <div
        className="overflow-hidden transition-all duration-300 ease-out"
        style={{ maxHeight: expanded ? '400px' : '0px', opacity: expanded ? 1 : 0 }}
      >
        <div className="space-y-2 mt-1 max-h-[400px] overflow-y-auto pr-1">
          {results.map((r, i) => (
            <a
              key={i}
              href={r.url}
              target="_blank"
              rel="noopener noreferrer"
              className="block px-3 py-2 rounded-lg border transition-all"
              style={{ background: 'var(--bg-base-secondary)', borderColor: 'var(--border-neutral-l1)' }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'var(--border-neutral-l2)'
                e.currentTarget.style.background = 'var(--bg-overlay-l1)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--border-neutral-l1)'
                e.currentTarget.style.background = 'var(--bg-base-secondary)'
              }}
            >
              <div className="flex items-start gap-2">
                <img
                  src={getFavicon(r.url)}
                  alt=""
                  className="w-4 h-4 rounded-sm flex-shrink-0 mt-0.5"
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] font-mono flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>{i + 1}</span>
                    <span className="text-xs truncate font-medium" style={{ color: 'var(--text-default)' }}>{r.title}</span>
                  </div>
                  <p className="text-[11px] mt-1 line-clamp-2 leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{r.content}</p>
                  <span className="text-[10px] truncate block mt-1" style={{ color: 'var(--text-tertiary)' }}>{getDomain(r.url)}</span>
                </div>
              </div>
            </a>
          ))}
        </div>
      </div>
    </div>
  )
}
