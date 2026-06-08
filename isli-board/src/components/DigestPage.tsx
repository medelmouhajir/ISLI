import { Newspaper, CheckCheck } from 'lucide-react'
import { useState } from 'react'
import { cn } from '@/lib/utils'
import {
  useDigestNotifications,
  useMarkRead,
  useMarkAllRead,
  useDismissNotification,
} from '@/hooks/useNotifications'
import { NotificationItemRow } from './NotificationItem'
import { NotificationDetailModal } from './NotificationDetailModal'
import type { NotificationItem } from '@/types'

export function DigestPage() {
  const [filter, setFilter] = useState<'all' | 'unread' | 'read'>('all')
  const [selectedNotification, setSelectedNotification] = useState<NotificationItem | null>(null)
  const { data, isLoading } = useDigestNotifications(filter)
  const markRead = useMarkRead()
  const markAllRead = useMarkAllRead()
  const dismiss = useDismissNotification()

  const items = data?.items ?? []
  const unreadCount = data?.unread_count ?? 0

  return (
    <div className="flex-1 overflow-y-auto bg-bg-base h-full w-full min-h-0">
      <div className="p-6 md:p-8 max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-accent-amber/10 border border-accent-amber/20 flex items-center justify-center text-accent-amber">
            <Newspaper className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-sm font-display font-bold text-text-primary uppercase tracking-wider">
              Digest
            </h1>
            <p className="text-[10px] text-text-muted font-mono-data">
              Batched summaries of low-priority activity
            </p>
          </div>
          {unreadCount > 0 && (
            <span className="ml-auto text-[10px] font-mono-data text-accent-amber bg-accent-amber/10 border border-accent-amber/20 px-2 py-0.5 rounded-none">
              {unreadCount} unread
            </span>
          )}
        </div>

        {/* Toolbar */}
        <div className="flex items-center gap-3 mb-6">
          {(['all', 'unread', 'read'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={cn(
                'px-3 py-1.5 text-[10px] font-mono-data uppercase tracking-wider rounded-none border transition-colors',
                filter === f
                  ? 'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/30'
                  : 'bg-bg-elevated text-text-muted border-border-dim hover:text-text-secondary'
              )}
            >
              {f}
            </button>
          ))}
          {unreadCount > 0 && (
            <button
              onClick={() => markAllRead.mutate()}
              className={cn(
                'ml-auto inline-flex items-center gap-1.5 px-2 py-1.5 rounded-none',
                'text-[10px] font-mono-data uppercase tracking-wider',
                'bg-accent-green/10 text-accent-green border border-accent-green/20',
                'hover:bg-accent-green/20 transition-colors'
              )}
            >
              <CheckCheck className="w-3 h-3" />
              Mark All Read
            </button>
          )}
        </div>

        {/* List */}
        <div className="space-y-2">
          {isLoading && (
            <div className="flex items-center justify-center py-12">
              <div className="w-5 h-5 border-2 border-accent-cyan/30 border-t-accent-cyan rounded-full animate-spin" />
            </div>
          )}
          {!isLoading && items.length === 0 && (
            <div className="flex flex-col items-center justify-center py-20 text-text-muted">
              <Newspaper className="w-12 h-12 mb-4 opacity-20" />
              <p className="text-xs font-mono-data">No digests yet</p>
              <p className="text-[10px] text-text-muted mt-1 max-w-xs text-center">
                Low-priority notifications are batched and delivered here periodically.
              </p>
            </div>
          )}
          {items.map((item) => (
            <div key={item.id} className="group relative">
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

      <NotificationDetailModal
        open={!!selectedNotification}
        notification={selectedNotification}
        onMarkRead={(id) => markRead.mutate(id)}
        onDismiss={(id) => dismiss.mutate(id)}
        onClose={() => setSelectedNotification(null)}
      />
    </div>
  )
}

