import { useEffect, useRef, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { motion, AnimatePresence } from 'framer-motion'
import { Portal } from './Portal'

interface ModalProps {
  open: boolean
  onClose: () => void
  title?: string
  showClose?: boolean
  children: ReactNode
  className?: string
  noPadding?: boolean
  scrollable?: boolean
}

export function Modal({ 
  open, 
  onClose, 
  title, 
  showClose = true, 
  children, 
  className,
  noPadding = false,
  scrollable = true
}: ModalProps) {
  const contentRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return

    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKey)

    return () => {
      document.removeEventListener('keydown', handleKey)
    }
  }, [open, onClose])

  useEffect(() => {
    if (!open) return

    const timer = setTimeout(() => {
      const focusable = contentRef.current?.querySelector<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
      focusable?.focus()
    }, 50)

    // Prevent body scroll
    document.body.style.overflow = 'hidden'

    return () => {
      clearTimeout(timer)
      document.body.style.overflow = ''
    }
  }, [open])

  const hasHeader = title || showClose

  return (
    <AnimatePresence>
      {open && (
        <Portal>
          <div
            className="fixed inset-0 z-[100] overflow-y-auto p-4 sm:p-6"
            role="dialog"
            aria-modal="true"
            aria-labelledby="modal-title"
          >
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              onClick={onClose}
            />
            
            {/* Centering Wrapper */}
            <div className="flex min-h-full items-end sm:items-center justify-center pointer-events-none">
              <motion.div
                ref={contentRef}
                initial={{ opacity: 0, y: "100%" }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: "100%" }}
                transition={{ type: 'spring', damping: 25, stiffness: 400 }}
                className={cn(
                  'relative bg-bg-surface border border-border-bright rounded-t-xl sm:rounded-none',
                  'w-full sm:max-w-md shadow-2xl pointer-events-auto',
                  'flex flex-col max-h-[90vh] sm:max-h-none overflow-hidden',
                  className
                )}
              >
                {hasHeader && (
                  <div className="shrink-0 flex items-center justify-between px-5 sm:px-6 py-4 border-b border-border-dim bg-bg-surface rounded-none">
                    <h2 id="modal-title" className="text-lg font-display font-semibold text-text-primary">
                      {title || ''}
                    </h2>
                    {showClose && (
                      <button
                        onClick={onClose}
                        aria-label="Close dialog"
                        className="w-8 h-8 rounded-none flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors border border-transparent hover:border-border-dim"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                )}
                {scrollable ? (
                  <div className={cn("flex-1 overflow-y-auto custom-scrollbar", !noPadding && "px-5 sm:px-6 py-5")}>
                    {children}
                  </div>
                ) : (
                  children
                )}
              </motion.div>
            </div>
          </div>
        </Portal>
      )}
    </AnimatePresence>
  )
}
