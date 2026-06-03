import { LabelHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

interface LabelProps extends LabelHTMLAttributes<HTMLLabelElement> {}

export const Label = ({ className, children, ...props }: LabelProps) => {
  return (
    <label
      className={cn(
        'block text-[10px] font-mono font-medium uppercase tracking-wider text-text-secondary mb-1.5 ml-0.5',
        className
      )}
      {...props}
    >
      {children}
    </label>
  )
}
