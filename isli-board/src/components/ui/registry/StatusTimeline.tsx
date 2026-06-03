import type { UiComponentProps } from './UiComponentRegistry'
import { cn } from '@/lib/utils'
import { Check, Loader2, X, Clock } from 'lucide-react'

interface TimelineStep {
  label: string
  status: 'completed' | 'in_progress' | 'pending' | 'failed'
  detail?: string
}

export function StatusTimeline({ payload }: UiComponentProps) {
  const { props } = payload
  const steps = (props.steps ?? []) as TimelineStep[]

  return (
    <div className="border border-border-dim bg-bg-elevated p-4 space-y-0">
      {steps.map((step, i) => {
        const isLast = i === steps.length - 1
        const statusConfig = {
          completed: {
            dotClass: 'bg-accent-green border-accent-green',
            icon: <Check className="w-3 h-3 text-bg-base" />,
            lineClass: 'bg-accent-green/30',
          },
          in_progress: {
            dotClass: 'bg-accent-amber border-accent-amber animate-pulse',
            icon: <Loader2 className="w-3 h-3 text-bg-base animate-spin" />,
            lineClass: 'bg-border-dim',
          },
          pending: {
            dotClass: 'bg-bg-surface border-border-dim',
            icon: <Clock className="w-3 h-3 text-text-muted" />,
            lineClass: 'bg-border-dim',
          },
          failed: {
            dotClass: 'bg-accent-red border-accent-red',
            icon: <X className="w-3 h-3 text-bg-base" />,
            lineClass: 'bg-accent-red/20',
          },
        }[step.status] ?? {
          dotClass: 'bg-bg-surface border-border-dim',
          icon: <Clock className="w-3 h-3 text-text-muted" />,
          lineClass: 'bg-border-dim',
        }

        return (
          <div key={i} className="flex">
            {/* Dot column */}
            <div className="flex flex-col items-center mr-3">
              <div
                className={cn(
                  'w-5 h-5 rounded-none flex items-center justify-center border shrink-0',
                  statusConfig.dotClass
                )}
              >
                {statusConfig.icon}
              </div>
              {!isLast && (
                <div
                  className={cn(
                    'w-px flex-1 min-h-[16px]',
                    statusConfig.lineClass
                  )}
                />
              )}
            </div>
            {/* Content column */}
            <div className={cn('pb-3', isLast && 'pb-0')}>
              <div className="text-[11px] font-mono font-bold text-text-primary uppercase tracking-tight">
                {step.label}
              </div>
              {step.detail && (
                <div className="text-[10px] font-mono text-text-muted mt-0.5">
                  {step.detail}
                </div>
              )}
            </div>
          </div>
        )
      })}
      {steps.length === 0 && (
        <div className="text-[11px] font-mono text-text-muted">No steps</div>
      )}
    </div>
  )
}
