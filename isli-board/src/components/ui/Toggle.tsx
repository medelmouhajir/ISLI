import { cn } from '@/lib/utils'

interface ToggleProps {
  checked: boolean
  onChange: (checked: boolean) => void
  label?: string
  disabled?: boolean
}

export function Toggle({ checked, onChange, label, disabled }: ToggleProps) {
  return (
    <label
      className={cn(
        'flex items-center gap-2 cursor-pointer select-none',
        disabled && 'opacity-30 cursor-not-allowed'
      )}
    >
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative w-7 h-4 rounded-none border transition-all duration-150',
          checked
            ? 'bg-accent-cyan/20 border-accent-cyan'
            : 'bg-bg-elevated border-border-dim'
        )}
      >
        <span
          className={cn(
            'absolute top-0.5 left-0.5 w-2.5 h-2.5 bg-text-primary transition-transform duration-150',
            checked && 'translate-x-3 bg-accent-cyan'
          )}
        />
      </button>
      {label && (
        <span className="text-[9px] font-mono font-bold text-text-muted uppercase tracking-widest">
          {label}
        </span>
      )}
    </label>
  )
}
