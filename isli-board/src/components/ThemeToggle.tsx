import { Sun, Moon, Monitor } from 'lucide-react'
import { useTheme } from '@/hooks/useTheme'
import { cn } from '@/lib/utils'

interface ThemeToggleProps {
  className?: string
  variant?: 'icon' | 'segmented'
}

export function ThemeToggle({ className, variant = 'icon' }: ThemeToggleProps) {
  const { theme, resolvedTheme, setTheme } = useTheme()

  if (variant === 'segmented') {
    return (
      <div
        className={cn(
          'inline-flex items-center rounded-lg border border-border-dim bg-bg-surface p-0.5',
          className
        )}
      >
        <button
          onClick={() => setTheme('light')}
          className={cn(
            'flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors',
            theme === 'light'
              ? 'bg-bg-elevated text-text-primary shadow-sm'
              : 'text-text-muted hover:text-text-secondary'
          )}
          aria-label="Light mode"
          title="Light mode"
        >
          <Sun className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Light</span>
        </button>
        <button
          onClick={() => setTheme('dark')}
          className={cn(
            'flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors',
            theme === 'dark'
              ? 'bg-bg-elevated text-text-primary shadow-sm'
              : 'text-text-muted hover:text-text-secondary'
          )}
          aria-label="Dark mode"
          title="Dark mode"
        >
          <Moon className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Dark</span>
        </button>
        <button
          onClick={() => setTheme('system')}
          className={cn(
            'flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors',
            theme === 'system'
              ? 'bg-bg-elevated text-text-primary shadow-sm'
              : 'text-text-muted hover:text-text-secondary'
          )}
          aria-label="System preference"
          title="System preference"
        >
          <Monitor className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Auto</span>
        </button>
      </div>
    )
  }

  return (
    <button
      onClick={() => setTheme(resolvedTheme === 'light' ? 'dark' : 'light')}
      className={cn(
        'inline-flex items-center justify-center rounded-lg',
        'w-8 h-8 sm:w-9 sm:h-9',
        'border border-border-dim bg-bg-surface text-text-secondary',
        'hover:border-border-bright hover:text-text-primary hover:bg-bg-elevated',
        'transition-all duration-200',
        className
      )}
      aria-label={resolvedTheme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
      title={resolvedTheme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
    >
      {resolvedTheme === 'light' ? (
        <Moon className="w-4 h-4" />
      ) : (
        <Sun className="w-4 h-4" />
      )}
    </button>
  )
}
