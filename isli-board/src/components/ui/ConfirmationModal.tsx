import { Modal } from './Modal'
import { Button } from './Button'
import { AlertTriangle, Info, AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ConfirmationModalProps {
  open: boolean
  onClose: () => void
  onConfirm: () => void | Promise<void>
  title: string
  description?: string
  confirmText?: string
  cancelText?: string
  variant?: 'danger' | 'warning' | 'primary'
  isLoading?: boolean
}

export function ConfirmationModal({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  variant = 'primary',
  isLoading = false,
}: ConfirmationModalProps) {
  const Icon = variant === 'danger' ? AlertCircle : variant === 'warning' ? AlertTriangle : Info
  const iconColor = variant === 'danger' ? 'text-accent-red' : variant === 'warning' ? 'text-accent-amber' : 'text-accent-cyan'

  const handleConfirm = async () => {
    try {
      await onConfirm()
      onClose()
    } catch (err) {
      console.error('Confirmation action failed:', err)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={title} className="sm:max-w-md">
      <div className="flex flex-col items-center text-center space-y-6">
        <div className={cn(
          "p-4 border rounded-none transition-colors",
          variant === 'danger' ? "bg-accent-red/5 border-accent-red/20" :
          variant === 'warning' ? "bg-accent-amber/5 border-accent-amber/20" :
          "bg-accent-cyan/5 border-accent-cyan/20",
          iconColor
        )}>
          <Icon className="w-8 h-8" />
        </div>
        
        {description && (
          <p className="text-sm text-text-secondary leading-relaxed font-mono">
            {description}
          </p>
        )}

        <div className="flex flex-col w-full gap-3 pt-4">
          <Button
            onClick={handleConfirm}
            variant={variant === 'danger' ? 'danger' : 'primary'}
            disabled={isLoading}
            className={cn(
              "w-full h-12 text-xs tracking-[0.2em] font-bold uppercase rounded-none",
              variant === 'warning' && "bg-accent-amber border-accent-amber hover:bg-accent-amber/90 text-black",
              variant === 'primary' && "bg-accent-cyan border-accent-cyan hover:bg-accent-cyan/90 text-black",
              variant === 'danger' && "bg-accent-red border-accent-red hover:bg-accent-red/90 text-white"
            )}
          >
            {isLoading ? 'PROCESSING...' : confirmText.toUpperCase()}
          </Button>
          <button
            onClick={onClose}
            disabled={isLoading}
            className="w-full py-3 text-[10px] tracking-[0.2em] text-text-muted hover:text-text-primary uppercase font-bold transition-colors disabled:opacity-50"
          >
            {cancelText.toUpperCase()}
          </button>
        </div>
      </div>
    </Modal>
  )
}
