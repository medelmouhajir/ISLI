import { useState } from 'react'
import { X, Bell, Newspaper } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'
import {
  useNotifications,
  useDigestNotifications,
  useMarkRead,
  useMarkAllRead,
  useDismissNotification,
} from '@/hooks/useNotifications'
import { NotificationItemRow } from './NotificationItem'
import { NotificationDetailModal } from './NotificationDetailModal'
import { Portal } from './ui/Portal'
import type { NotificationItem } from '@/types'

interface NotificationDrawerProps {
  open: boolean
  onClose: () => void
}

export function NotificationDrawer({ open, onClose }: NotificationDrawerProps) {
  const [tab, setTab] = useState<'inbox' | 'digest'>('inbox')
  const [filter, setFilter] = useState<'all' | 'unread' | 'read'>('all')
  const [selectedNotification, setSelectedNotification] = useState<NotificationItem | null>(null)

  const inboxQuery = useNotifications(filter)
  const digestQuery = useDigestNotifications(filter)
  const markRead = useMarkRead()
  const markAllRead = useMarkAllRead()
  const dismiss = useDismissNotification()

  const isDigest = tab === 'digest'
  const { data, isLoading } = isDigest ? digestQuery : inboxQuery
  const items = data?.items ?? []
  const unreadCount = data?.unread_count ?? 0

  return (
    <>
      <AnimatePresence>
        {open && (
          <Portal>
            <div className="fixed inset-0 z-50 flex justify-end">
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="absolute inset-0 bg-black/60 backdrop-blur-[2px]"
                onClick={onClose}
              />
              <motion.div
                initial={{ x: '100%' }}
                animate={{ x: 0 }}
                exit={{ x: '100%' }}
                transition={{ type: 'tween', duration: 0.2, ease: 'easeOut' }}
                className={cn(
                  'relative bg-bg-surface border-l border-border-dim',
                  'w-full max-w-md h-screen flex flex-col z-50 overflow-hidden'
                )}
              >
                {/* Header */}
                <div className="shrink-0 flex items-center justify-between px-4 py-3 border-b border-border-bright bg-bg-surface">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 bg-accent-cyan flex items-center justify-center text-black">
                      <Bell className="w-4 h-4" />
                    </div>
                    <div className="flex flex-col">
                      <h2 className="text-xs font-mono-data font-bold text-text-primary uppercase tracking-[0.15em]">
                        Activity Ledger
                      </h2>
                      {unreadCount > 0 && (
                        <span className="text-[10px] text-accent-red font-mono-data uppercase">
                          [{unreadCount} UNREAD]
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {unreadCount > 0 && (
                      <button
                        onClick={() => markAllRead.mutate()}
                        className={cn(
                          'px-2 py-1 bg-bg-elevated border border-border-dim',
                          'text-[9px] font-mono-data uppercase tracking-wider text-text-secondary',
                          'hover:bg-accent-green hover:text-black hover:border-accent-green transition-all'
                        )}
                      >
                        Mark All
                      </button>
                    )}
                    <button
                      onClick={onClose}
                      className="w-8 h-8 flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-bg-elevated border border-border-dim transition-colors"
                      aria-label="Close"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* View Switch */}
                <div className="shrink-0 grid grid-cols-2 border-b border-border-dim">
                  <button
                    onClick={() => setTab('inbox')}
                    className={cn(
                      'py-2.5 text-[10px] font-mono-data uppercase tracking-widest border-r border-border-dim transition-all',
                      tab === 'inbox'
                        ? 'bg-text-primary text-bg-surface'
                        : 'bg-bg-surface text-text-muted hover:text-text-secondary hover:bg-bg-elevated'
                    )}
                  >
                    01_INBOX
                  </button>
                  <button
                    onClick={() => setTab('digest')}
                    className={cn(
                      'py-2.5 text-[10px] font-mono-data uppercase tracking-widest transition-all',
                      tab === 'digest'
                        ? 'bg-text-primary text-bg-surface'
                        : 'bg-bg-surface text-text-muted hover:text-text-secondary hover:bg-bg-elevated'
                    )}
                  >
                    02_DIGEST
                  </button>
                </div>

                {/* Filter Row */}
                <div className="shrink-0 flex items-center gap-1 p-2 bg-bg-base border-b border-border-dim">
                  <span className="text-[9px] font-mono-data text-text-muted uppercase px-2">Filter:</span>
                  {(['all', 'unread', 'read'] as const).map((f) => (
                    <button
                      key={f}
                      onClick={() => setFilter(f)}
                      className={cn(
                        'px-2 py-0.5 text-[9px] font-mono-data uppercase border transition-all',
                        filter === f
                          ? 'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/40'
                          : 'bg-bg-surface text-text-muted border-border-dim hover:border-border-bright'
                      )}
                    >
                      {f}
                    </button>
                  ))}
                </div>

                {/* Ledger List */}
                <div className="flex-1 overflow-y-auto custom-scrollbar bg-bg-base/30">
                  {isLoading && (
                    <div className="flex items-center justify-center py-12">
                      <div className="w-4 h-4 border border-accent-cyan border-t-transparent animate-spin" />
                    </div>
                  )}
                  {!isLoading && items.length === 0 && (
                    <div className="flex flex-col items-center justify-center py-24 text-text-muted">
                      <div className="w-12 h-12 border border-border-dim flex items-center justify-center mb-4 opacity-20">
                        {isDigest ? <Newspaper className="w-6 h-6" /> : <Bell className="w-6 h-6" />}
                      </div>
                      <p className="text-[10px] font-mono-data uppercase tracking-widest">
                        Void_State_Detected
                      </p>
                    </div>
                  )}
                  <div className="divide-y divide-border-dim">
                    {items.map((item: NotificationItem) => (
                      <div key={item.id} className="group">
                        <NotificationItemRow
                          item={item}
                          onMarkRead={() => markRead.mutate(item.id)}
                          onDismiss={() => dismiss.mutate(item.id)}
                          onClick={() => setSelectedNotification(item)}
                        />
                      </div>
                    ))}
                  </div>
                </div>

                {/* Footer Status */}
                <div className="shrink-0 h-6 bg-bg-elevated border-t border-border-dim flex items-center justify-between px-3">
                  <div className="flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-accent-green animate-pulse" />
                    <span className="text-[8px] font-mono-data text-text-muted uppercase tracking-tighter">
                      System_Ready // Connection_Live
                    </span>
                  </div>
                  <span className="text-[8px] font-mono-data text-text-muted uppercase">
                    {items.length} Record(s)
                  </span>
                </div>
              </motion.div>
            </div>
          </Portal>
        )}
      </AnimatePresence>

      <NotificationDetailModal
        open={!!selectedNotification}
        notification={selectedNotification}
        onMarkRead={(id) => markRead.mutate(id)}
        onDismiss={(id) => dismiss.mutate(id)}
        onClose={() => setSelectedNotification(null)}
      />
    </>
  )
}
