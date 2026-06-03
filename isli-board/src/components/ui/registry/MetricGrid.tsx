import type { UiComponentProps } from './UiComponentRegistry'
import { cn } from '@/lib/utils'
import { ArrowUp, ArrowDown, Minus } from 'lucide-react'

interface Metric {
  label: string
  value: string
  trend?: 'up' | 'down' | 'flat'
  color?: 'cyan' | 'amber' | 'green' | 'red' | 'violet'
}

const colorMap: Record<string, { text: string; border: string; bg: string }> = {
  cyan: { text: 'text-accent-cyan', border: 'border-accent-cyan/20', bg: 'bg-accent-cyan/5' },
  amber: { text: 'text-accent-amber', border: 'border-accent-amber/20', bg: 'bg-accent-amber/5' },
  green: { text: 'text-accent-green', border: 'border-accent-green/20', bg: 'bg-accent-green/5' },
  red: { text: 'text-accent-red', border: 'border-accent-red/20', bg: 'bg-accent-red/5' },
  violet: { text: 'text-accent-violet', border: 'border-accent-violet/20', bg: 'bg-accent-violet/5' },
}

const trendIcon = {
  up: <ArrowUp className="w-3 h-3" />,
  down: <ArrowDown className="w-3 h-3" />,
  flat: <Minus className="w-3 h-3" />,
}

const trendColor = {
  up: 'text-accent-green',
  down: 'text-accent-red',
  flat: 'text-text-muted',
}

export function MetricGrid({ payload }: UiComponentProps) {
  const { props } = payload
  const metrics = (props.metrics ?? []) as Metric[]

  return (
    <div className="border border-border-dim bg-bg-elevated p-4">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
        {metrics.map((metric, i) => {
          const colors = colorMap[metric.color ?? 'cyan'] ?? colorMap.cyan
          return (
            <div
              key={i}
              className={cn(
                'border p-3 flex flex-col justify-between',
                colors.border,
                colors.bg
              )}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-[9px] font-mono font-bold text-text-muted uppercase tracking-widest">
                  {metric.label}
                </span>
                {metric.trend && (
                  <span className={cn('flex items-center', trendColor[metric.trend])}>
                    {trendIcon[metric.trend]}
                  </span>
                )}
              </div>
              <span className={cn('text-lg font-mono font-bold tracking-tight', colors.text)}>
                {metric.value}
              </span>
            </div>
          )
        })}
      </div>
      {metrics.length === 0 && (
        <div className="text-[11px] font-mono text-text-muted">No metrics</div>
      )}
    </div>
  )
}
