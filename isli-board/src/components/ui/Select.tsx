import { forwardRef, type SelectHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...props }, ref) => {
    return (
      <div className="industrial-focus-wrapper">
        <select
          ref={ref}
          className={cn(
            'w-full bg-bg-surface border border-border-dim rounded-none px-3.5 py-2.5 text-sm text-text-primary',
            'font-mono focus:outline-none focus:border-accent-cyan',
            'hover:border-border-bright',
            'transition-all duration-200 appearance-none',
            'bg-[url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 24 24\' fill=\'%236b7280\'%3E%3Cpath d=\'M7 10l5 5 5-5z\'/%3E%3C/svg%3E")] bg-no-repeat bg-right-3 bg-[length:20px] pr-10',
            className
          )}
          {...props}
        >
          {children}
        </select>

      </div>
    )
  }
)
Select.displayName = 'Select'
