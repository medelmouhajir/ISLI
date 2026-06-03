import { useAuth } from '@/hooks/useAuth'
import { Button } from '@/components/ui/Button'
import { ShieldCheck, LogOut } from 'lucide-react'

export function AuthStatus() {
  const { isAuthenticated, logout } = useAuth()

  if (!isAuthenticated) return null

  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-1.5 px-2 py-1 rounded border border-accent-green/30 bg-accent-green/10">
        <ShieldCheck className="w-3.5 h-3.5 text-accent-green" />
        <span className="hidden sm:inline text-[10px] font-mono-data uppercase tracking-wider text-accent-green">Authenticated</span>
      </div>
      <Button variant="ghost" size="sm" onClick={logout} className="gap-1.5">
        <LogOut className="w-3.5 h-3.5" />
        <span className="hidden sm:inline">Logout</span>
      </Button>
    </div>
  )
}
