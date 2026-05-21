import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          'inline-flex items-center justify-center rounded-lg font-display font-semibold transition-all duration-200',
          'focus:outline-none focus:ring-2 focus:ring-accent-cyan/30 focus:ring-offset-1 focus:ring-offset-bg-base',
          'disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]',
          {
            'bg-accent-cyan text-white hover:bg-accent-cyan/90 shadow-glow-cyan': variant === 'primary',
            'bg-bg-surface text-text-primary border border-border-dim hover:border-border-bright hover:bg-bg-elevated hover:shadow-card': variant === 'secondary',
            'bg-accent-red text-white hover:bg-accent-red/90 shadow-glow-red': variant === 'danger',
            'bg-transparent text-text-secondary hover:text-text-primary hover:bg-bg-surface/50': variant === 'ghost',
            'px-2 py-1 text-xs': size === 'sm',
            'px-3.5 py-2 text-sm': size === 'md',
            'px-5 py-2.5 text-base': size === 'lg',
          },
          className
        )}
        {...props}
      />
    )
  }
)
Button.displayName = 'Button'
