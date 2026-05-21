import { forwardRef, type TextareaHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        ref={ref}
        className={cn(
          'w-full bg-bg-surface border border-border-dim rounded-lg px-3.5 py-2.5 text-sm text-text-primary',
          'placeholder:text-text-muted resize-y min-h-[80px]',
          'focus:outline-none focus:border-accent-cyan/50 focus:ring-2 focus:ring-accent-cyan/10',
          'hover:border-border-bright',
          'transition-all duration-200',
          className
        )}
        {...props}
      />
    )
  }
)
Textarea.displayName = 'Textarea'
