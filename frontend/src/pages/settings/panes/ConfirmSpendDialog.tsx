// ConfirmSpendDialog 烧钱动作统一确认弹窗（delta add-eval-ops-console Task 6）
//
// 三个烧钱动作（cohort 开启 / 正式批 / 探针单跑）共用本组件：确认前不发任何请求；
// 取消（含点遮罩 / ESC / 右上角关闭）只回调 onCancel，调用方不得在取消路径上发请求。
// 成本量级数字来源：预登记「成本分型」字段（可用时）+ 动作规模换算（标的数 × 重复数）。
import { Button } from '../../../components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from '../../../components/ui/dialog'

export interface SpendConfirmRequest {
  /** 动作名（如「开启 cohort 跑批」），出现在标题与确认按钮上 */
  title: string
  /** 成本/规模估算行（首行须含 tokens 量级与来源说明） */
  estimate: string[]
  /** 当前预算上限（含今日已花费） */
  budget: string
  confirmLabel?: string
}

export function ConfirmSpendDialog(props: {
  request: SpendConfirmRequest | null
  onConfirm: () => void
  onCancel: () => void
}) {
  const { request, onConfirm, onCancel } = props
  // 未在确认态时不渲染任何内容（不产生隐藏的对话框树）
  if (request === null) return null
  return (
    <Dialog open onOpenChange={(open) => { if (!open) onCancel() }}>
      <DialogContent data-testid="eval-ops-confirm-dialog" className="max-w-md">
        <DialogTitle className="text-sm font-semibold" style={{ color: 'var(--text-default)' }}>
          确认{request.title}
        </DialogTitle>
        <DialogDescription className="text-xs" style={{ color: 'var(--text-secondary)' }}>
          该动作会产生 LLM 调用与 token 花费；确认后才会发起请求，取消不产生任何变更。
        </DialogDescription>

        <div className="rounded-lg p-3 space-y-1" style={{ background: 'var(--bg-overlay-l1)' }}>
          <div className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>成本 / 规模估算</div>
          <div data-testid="eval-ops-confirm-cost" className="text-xs space-y-1" style={{ color: 'var(--text-default)' }}>
            {request.estimate.map((line) => <div key={line}>{line}</div>)}
          </div>
          <div data-testid="eval-ops-confirm-budget" className="text-xs pt-1" style={{ color: 'var(--text-secondary)' }}>
            {request.budget}
          </div>
        </div>

        <DialogFooter className="gap-2">
          <Button data-testid="eval-ops-confirm-cancel" variant="secondary" size="sm" onClick={onCancel}>
            取消
          </Button>
          <Button data-testid="eval-ops-confirm-ok" size="sm" onClick={onConfirm}>
            {request.confirmLabel ?? '确认发起'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
