import { useRef } from 'react'
import { cn } from '@/lib/utils'
import { Menu } from 'lucide-react'
import { Link } from 'react-router-dom'
import { AuthStatus } from '@/components/AuthStatus'
import { NotificationBell } from '@/components/NotificationBell'

interface HeaderProps {
  onToggleMobileSidebar?: (page?: number) => void
  mobileNavOpen?: boolean
}

export function Header({ onToggleMobileSidebar, mobileNavOpen }: HeaderProps) {
  const touchStartY = useRef<number | null>(null)

  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartY.current = e.touches[0].clientY
  }

  const handleTouchEnd = (e: React.TouchEvent) => {
    if (touchStartY.current === null) return
    
    const touchEndY = e.changedTouches[0].clientY
    const deltaY = touchEndY - touchStartY.current
    
    // If pulled down more than 50px, open sidebar to Agents interface (page 1)
    if (deltaY > 50 && onToggleMobileSidebar) {
      onToggleMobileSidebar(1)
    }
    
    touchStartY.current = null
  }

  return (
    <header 
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
      className={cn(
      'relative z-20 border-b border-border-dim bg-bg-surface/80 backdrop-blur-xl px-4 sm:px-6 py-3 flex items-center justify-between touch-none sm:touch-auto',
      mobileNavOpen && 'hidden md:flex'
    )}>
      <div className="flex items-center gap-3">
        <button
          onClick={() => onToggleMobileSidebar?.(0)}
          className="lg:hidden inline-flex items-center justify-center w-8 h-8 rounded-none border border-border-dim bg-bg-elevated text-text-secondary hover:text-text-primary hover:border-border-bright transition-colors"
          aria-label="Open sidebar"
        >
          <Menu className="w-4 h-4" />
        </button>
        <Link
          to="/"
          className="flex items-center gap-2.5 transition-all hover:opacity-80 group"
        >
          <img src="/favicon.png" alt="ISLI" className="w-6 h-6 rounded-none group-hover:scale-110 transition-transform" />
          <h1 className="text-lg sm:text-xl font-display font-bold tracking-wider text-text-primary">
            ISLI<span className="text-accent-cyan">.</span>BOARD
          </h1>
        </Link>
        <span className="hidden sm:inline-flex text-[10px] px-2 py-0.5 rounded-none bg-bg-elevated text-text-secondary border border-border-dim font-mono-data">
          v1.0
        </span>
      </div>

      <div className="flex items-center gap-2 sm:gap-3">
        <NotificationBell />
        <AuthStatus />
      </div>
    </header>
  )
}
