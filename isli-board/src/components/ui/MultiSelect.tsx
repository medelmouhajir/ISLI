import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface MultiSelectOption {
  value: string
  label: string
  badge?: string
  badgeVariant?: 'cyan' | 'amber'
  description?: string
  group?: string
}

interface MultiSelectProps {
  options: MultiSelectOption[]
  selected: string[]
  onChange: (selected: string[]) => void
  emptyMessage?: string
}

export function MultiSelect({
  options,
  selected,
  onChange,
  emptyMessage = 'No options available',
}: MultiSelectProps) {
  const toggle = (value: string) => {
    if (selected.includes(value)) {
      onChange(selected.filter((v) => v !== value))
    } else {
      onChange([...selected, value])
    }
  }

  if (options.length === 0) {
    return (
      <p className="text-xs text-text-muted italic py-4">{emptyMessage}</p>
    )
  }

  // Sort by group so headers appear in a predictable order; undefined groups sort last
  const sorted = [...options].sort((a, b) => {
    const ga = a.group ?? '\x7f'
    const gb = b.group ?? '\x7f'
    if (ga !== gb) return ga.localeCompare(gb)
    return a.label.localeCompare(b.label)
  })

  let lastGroup: string | undefined

  return (
    <div className="space-y-2 max-h-[320px] overflow-y-auto pr-1">
      {sorted.map((opt) => {
        const isSelected = selected.includes(opt.value)
        const showHeader = opt.group && opt.group !== lastGroup
        if (showHeader) lastGroup = opt.group
        return (
          <div key={opt.value} className="space-y-2">
            {showHeader && (
              <div className="pt-2 pb-0.5 px-1">
                <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-text-muted/70">
                  {opt.group}
                </span>
              </div>
            )}
            <button
              type="button"
              onClick={() => toggle(opt.value)}
              className={cn(
                'w-full text-left px-4 py-3 rounded-none border transition-all duration-200 flex items-start gap-3',
                isSelected
                  ? 'bg-accent-cyan/10 border-accent-cyan shadow-glow-cyan/10'
                  : 'bg-bg-base/50 border-border-dim hover:border-border-bright hover:bg-bg-elevated/30'
              )}
            >
              <div
                className={cn(
                  'mt-0.5 w-4 h-4 rounded-none border flex items-center justify-center transition-colors shrink-0',
                  isSelected
                    ? 'bg-accent-cyan border-accent-cyan'
                    : 'border-border-dim'
                )}
              >
                {isSelected && <Check className="w-3 h-3 text-white" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span
                    className={cn(
                      'text-xs font-display font-bold',
                      isSelected ? 'text-accent-cyan' : 'text-text-primary'
                    )}
                  >
                    {opt.label}
                  </span>
                  {opt.badge && (
                    <span
                      className={cn(
                        'px-1.5 py-0.5 rounded-none text-[10px] font-bold uppercase tracking-wider border',
                        opt.badgeVariant === 'amber'
                          ? 'bg-accent-amber/10 text-accent-amber border-accent-amber/20'
                          : 'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/20'
                      )}
                    >
                      {opt.badge}
                    </span>
                  )}
                </div>
                {opt.description && (
                  <p className="text-[11px] text-text-secondary leading-relaxed mt-0.5 line-clamp-2">
                    {opt.description}
                  </p>
                )}
              </div>
            </button>
          </div>
        )
      })}
    </div>
  )
}
