import { cn } from '@/lib/utils'
import { Menu } from 'lucide-react'
import { Link } from 'react-router-dom'
import { AuthStatus } from '@/components/AuthStatus'
import { NotificationBell } from '@/components/NotificationBell'

interface HeaderProps {
  onToggleMobileSidebar?: () => void
  mobileNavOpen?: boolean
}

export function Header({ onToggleMobileSidebar, mobileNavOpen }: HeaderProps) {
  return (
    <header className={cn(
      'relative z-20 border-b border-border-dim bg-bg-surface/80 backdrop-blur-xl px-4 sm:px-6 py-3 flex items-center justify-between',
      mobileNavOpen && 'hidden md:flex'
    )}>
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleMobileSidebar}
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
