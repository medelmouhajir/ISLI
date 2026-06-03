import { cn } from '@/lib/utils'

interface BadgeProps {
  children: React.ReactNode
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'muted'
  className?: string
}

const variantStyles: Record<string, string> = {
  default: 'bg-bg-elevated text-text-secondary border-border-dim',
  success: 'bg-accent-green/10 text-accent-green border-accent-green/20',
  warning: 'bg-accent-amber/10 text-accent-amber border-accent-amber/20',
  danger: 'bg-accent-red/10 text-accent-red border-accent-red/20',
  info: 'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/20',
  muted: 'bg-transparent text-text-muted border-transparent',
}

export function Badge({ children, variant = 'default', className }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded-none text-[11px] font-mono-data font-semibold border',
        variantStyles[variant],
        className
      )}
    >
      {children}
    </span>
  )
}
