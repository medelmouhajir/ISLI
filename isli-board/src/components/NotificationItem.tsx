import { cn } from '@/lib/utils'
import { AlertTriangle, CheckCircle2, Info, XCircle, Trash2, Check } from 'lucide-react'
import type { NotificationItem } from '@/types'

interface NotificationItemRowProps {
  item: NotificationItem
  onMarkRead: () => void
  onDismiss: () => void
}

const categoryConfig = {
  critical: { icon: AlertTriangle, color: 'text-black', bg: 'bg-accent-red', border: 'border-accent-red' },
  high: { icon: XCircle, color: 'text-black', bg: 'bg-accent-amber', border: 'border-accent-amber' },
  normal: { icon: Info, color: 'text-black', bg: 'bg-accent-cyan', border: 'border-accent-cyan' },
  low: { icon: CheckCircle2, color: 'text-text-muted', bg: 'bg-bg-elevated', border: 'border-border-dim' },
}

export function NotificationItemRow({ item, onMarkRead, onDismiss }: NotificationItemRowProps) {
  const config = categoryConfig[item.category] || categoryConfig.normal
  const isUnread = !item.read_at

  return (
    <div
      className={cn(
        'relative flex items-stretch gap-0 border-b border-border-dim/50 group transition-colors',
        isUnread ? 'bg-bg-surface' : 'bg-bg-base/40 opacity-60'
      )}
    >
      {/* Category Indicator Block */}
      <div className={cn('w-1 shrink-0', config.bg)} />

      <div className="flex-1 flex flex-col min-w-0 py-3 pl-3 pr-4">
        <div className="flex items-start justify-between gap-4 mb-1">
          <div className="flex items-center gap-2">
            <span className={cn(
              'text-[8px] font-mono-data font-bold uppercase px-1.5 py-0.5 tracking-tighter',
              config.bg, config.color
            )}>
              {item.category}
            </span>
            <span className="text-[9px] font-mono-data text-text-muted">
              {new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}
            </span>
          </div>
          
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            {isUnread && (
              <button
                onClick={onMarkRead}
                className="w-5 h-5 flex items-center justify-center text-text-muted hover:text-accent-green border border-border-dim hover:border-accent-green transition-colors"
                title="Mark Read"
              >
                <Check className="w-3 h-3" />
              </button>
            )}
            <button
              onClick={onDismiss}
              className="w-5 h-5 flex items-center justify-center text-text-muted hover:text-accent-red border border-border-dim hover:border-accent-red transition-colors"
              title="Dismiss"
            >
              <Trash2 className="w-3 h-3" />
            </button>
          </div>
        </div>

        <p className={cn(
          'text-[11px] font-mono-data leading-[1.3] mb-1',
          isUnread ? 'text-text-primary' : 'text-text-secondary'
        )}>
          {item.title}
        </p>

        {item.body && (
          <p className="text-[10px] font-mono-data text-text-muted leading-relaxed line-clamp-2">
            {item.body}
          </p>
        )}
      </div>
    </div>
  )
}

