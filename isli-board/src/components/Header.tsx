import { Cpu, Menu } from 'lucide-react'
import { Link } from 'react-router-dom'
import { AuthStatus } from '@/components/AuthStatus'
import { ThemeToggle } from '@/components/ThemeToggle'

interface HeaderProps {
  onLogin: () => void
  onToggleMobileSidebar?: () => void
}

export function Header({ onLogin, onToggleMobileSidebar }: HeaderProps) {
  return (
    <header className="relative z-20 border-b border-border-dim bg-bg-surface/80 backdrop-blur-xl px-4 sm:px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleMobileSidebar}
          className="lg:hidden inline-flex items-center justify-center w-8 h-8 rounded-lg border border-border-dim bg-bg-elevated text-text-secondary hover:text-text-primary hover:border-border-bright transition-colors"
          aria-label="Open sidebar"
        >
          <Menu className="w-4 h-4" />
        </button>
        <Link 
          to="/" 
          className="flex items-center gap-2.5 transition-all hover:opacity-80 group"
        >
          <div className="relative">
            <Cpu className="w-6 h-6 text-accent-cyan group-hover:scale-110 transition-transform" />
            <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-accent-green animate-pulse" />
          </div>
          <h1 className="text-lg sm:text-xl font-display font-bold tracking-wider text-text-primary">
            ISLI<span className="text-accent-cyan">.</span>BOARD
          </h1>
        </Link>
        <span className="hidden sm:inline-flex text-[10px] px-2 py-0.5 rounded-full bg-bg-elevated text-text-secondary border border-border-dim font-mono-data">
          v1.0
        </span>
      </div>

      <div className="flex items-center gap-2 sm:gap-3">
        <ThemeToggle />
        <AuthStatus onLogin={onLogin} />
      </div>
    </header>
  )
}
