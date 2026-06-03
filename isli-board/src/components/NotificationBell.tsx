import { useState } from 'react'
import { Bell } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUnreadCount } from '@/hooks/useNotifications'
import { NotificationDrawer } from './NotificationDrawer'

export function NotificationBell() {
  const [open, setOpen] = useState(false)
  const { data: unreadData } = useUnreadCount()
  const unread = unreadData?.unread_count ?? 0

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className={cn(
          'relative inline-flex items-center justify-center w-8 h-8 rounded-none',
          'border border-border-dim bg-bg-elevated text-text-secondary',
          'hover:text-accent-cyan hover:border-accent-cyan transition-all'
        )}
        aria-label="Notifications"
      >
        <Bell className="w-4 h-4" />
        {unread > 0 && (
          <span className="absolute -top-1.5 -right-1.5 h-4 px-1 flex items-center justify-center bg-accent-red text-black text-[9px] font-mono-data font-bold border border-bg-surface">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      <NotificationDrawer open={open} onClose={() => setOpen(false)} />
    </>
  )
}
