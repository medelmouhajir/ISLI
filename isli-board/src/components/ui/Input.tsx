import { forwardRef, type InputHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => {
    return (
      <div className="industrial-focus-wrapper">
        <input
          ref={ref}
          className={cn(
            'w-full bg-bg-surface border border-border-dim rounded-none px-3.5 py-2.5 text-sm text-text-primary',
            'placeholder:text-text-muted font-mono',
            'focus:outline-none focus:border-accent-cyan',
            'hover:border-border-bright',
            'transition-all duration-200',
            className
          )}
          {...props}
        />
      </div>
    )
  }
)
Input.displayName = 'Input'
