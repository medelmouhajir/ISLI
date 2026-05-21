import { cn } from '@/lib/utils'

interface StatusBadgeProps {
  status: string
  pulse?: boolean
}

const statusConfig: Record<string, { label: string; variant: string; dotColor: string; pulse: boolean }> = {
  online: { label: 'ONLINE', variant: 'success', dotColor: 'bg-accent-green', pulse: true },
  offline: { label: 'OFFLINE', variant: 'default', dotColor: 'bg-text-muted', pulse: false },
  paused: { label: 'PAUSED', variant: 'warning', dotColor: 'bg-accent-amber', pulse: false },
  registered: { label: 'REGISTERED', variant: 'info', dotColor: 'bg-accent-cyan', pulse: false },
  deleted: { label: 'DELETED', variant: 'danger', dotColor: 'bg-accent-red', pulse: false },
}

export function StatusBadge({ status, pulse: forcePulse }: StatusBadgeProps) {
  const config = statusConfig[status] || { label: status.toUpperCase(), variant: 'default', dotColor: 'bg-text-muted', pulse: false }
  const shouldPulse = forcePulse ?? config.pulse

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-mono-data font-semibold border',
        config.variant === 'success' && 'bg-accent-green/10 text-accent-green border-accent-green/20',
        config.variant === 'warning' && 'bg-accent-amber/10 text-accent-amber border-accent-amber/20',
        config.variant === 'danger' && 'bg-accent-red/10 text-accent-red border-accent-red/20',
        config.variant === 'info' && 'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/20',
        config.variant === 'default' && 'bg-bg-elevated text-text-secondary border-border-dim',
      )}
    >
      <span
        className={cn(
          'w-1.5 h-1.5 rounded-full',
          config.dotColor,
          shouldPulse && 'animate-pulse-glow'
        )}
      />
      {config.label}
    </span>
  )
}
