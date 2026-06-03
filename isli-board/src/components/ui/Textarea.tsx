import { forwardRef, type TextareaHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => {
    return (
      <div className="industrial-focus-wrapper">
        <textarea
          ref={ref}
          className={cn(
            'w-full bg-bg-surface border border-border-dim rounded-none px-3.5 py-2.5 text-sm text-text-primary',
            'placeholder:text-text-muted resize-y min-h-[80px] font-mono',
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
Textarea.displayName = 'Textarea'
