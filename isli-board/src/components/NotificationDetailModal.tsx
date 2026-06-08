import { Calendar, Hash, Bot, Layers, Check, Trash2, X } from 'lucide-react'
import { Modal } from '@/components/ui/Modal'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { JsonViewer } from '@/components/ui/registry/JsonViewer'
import { cn } from '@/lib/utils'
import type { NotificationItem } from '@/types'

interface NotificationDetailModalProps {
  open: boolean
  notification: NotificationItem | null
  onMarkRead: (id: string) => void
  onDismiss: (id: string) => void
  onClose: () => void
}

const categoryConfig = {
  critical: { variant: 'danger' as const, bg: 'bg-accent-red', text: 'text-accent-red' },
  high: { variant: 'warning' as const, bg: 'bg-accent-amber', text: 'text-accent-amber' },
  normal: { variant: 'info' as const, bg: 'bg-accent-cyan', text: 'text-accent-cyan' },
  low: { variant: 'default' as const, bg: 'bg-bg-elevated', text: 'text-text-muted' },
}

export function NotificationDetailModal({
  open,
  notification,
  onMarkRead,
  onDismiss,
  onClose,
}: NotificationDetailModalProps) {
  if (!notification) return null

  const config = categoryConfig[notification.category] || categoryConfig.normal
  const isUnread = !notification.read_at

  return (
    <Modal 
      open={open} 
      onClose={onClose} 
      showClose={false}
      noPadding={true}
      scrollable={false}
      className={cn(
        "max-w-xl border border-border-bright shadow-[0_0_60px_rgba(0,0,0,0.6)]",
        "w-full h-auto max-h-[90vh]",
        "flex flex-col rounded-none overflow-hidden"
      )}
    >
      {/* Industrial Status Bar (Edge-to-Edge) */}
      <div className={cn("h-1.5 w-full shrink-0", config.bg)} />

      {/* Content Area - Scrollable */}
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        <div className="p-5 sm:p-7 space-y-6">
          {/* Header Section */}
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-3">
                <Badge variant={config.variant} className="uppercase tracking-[0.1em] text-[9px] px-1.5 py-0">
                  {notification.category}
                </Badge>
                <span className="text-[9px] font-mono-data text-text-muted uppercase tracking-widest">
                  {notification.event_type}
                </span>
              </div>
              <h2 className="text-xl sm:text-2xl font-display font-bold text-text-primary leading-tight tracking-tight">
                {notification.title}
              </h2>
            </div>
            
            <button
              onClick={onClose}
              className="w-10 h-10 -mr-2 -mt-2 flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors border border-transparent hover:border-border-dim"
              aria-label="Close"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Metadata Grid - Industrial Table Style */}
          <div className="grid grid-cols-1 sm:grid-cols-2 border border-border-dim bg-bg-base/50">
            <MetaRow icon={<Hash className="w-3 h-3" />} label="ID" value={notification.id} />
            <MetaRow 
              icon={<Calendar className="w-3 h-3" />} 
              label="TS" 
              value={new Date(notification.created_at).toLocaleString()} 
            />
            {notification.agent_id && (
              <MetaRow icon={<Bot className="w-3 h-3" />} label="AGN" value={notification.agent_id} className="sm:border-t-0" />
            )}
            {notification.task_id && (
              <MetaRow icon={<Layers className="w-3 h-3" />} label="TSK" value={notification.task_id} className="sm:border-t-0" />
            )}
          </div>

          {/* Message Content */}
          {notification.body && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <div className="w-1 h-3 bg-text-muted/30" />
                <h3 className="text-[10px] font-mono-data uppercase tracking-[0.2em] text-text-muted">
                  Body_Content
                </h3>
              </div>
              <div className="bg-bg-elevated/40 border-l-2 border-border-dim p-4">
                <p className="text-[13px] sm:text-sm text-text-primary leading-relaxed whitespace-pre-wrap font-mono-data">
                  {notification.body}
                </p>
              </div>
            </div>
          )}

          {/* Payload Section */}
          {notification.payload && Object.keys(notification.payload).length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <div className="w-1 h-3 bg-text-muted/30" />
                <h3 className="text-[10px] font-mono-data uppercase tracking-[0.2em] text-text-muted">
                  System_Payload
                </h3>
              </div>
              <div className="border border-border-dim rounded-none overflow-hidden">
                <JsonViewer 
                  sessionId="static"
                  onAction={() => {}}
                  payload={{ 
                    component_type: 'json_viewer', 
                    props: { 
                      data: notification.payload,
                      collapsed: false 
                    } 
                  }} 
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Industrial Command Strip - Fixed to Modal Bottom */}
      <div className={cn(
        "shrink-0 p-4 sm:p-5 bg-bg-surface border-t border-border-bright",
        "flex flex-col sm:flex-row items-stretch sm:items-center justify-end gap-3"
      )}>
        <div className="hidden sm:flex items-center gap-2 mr-auto text-[9px] font-mono-data text-text-muted uppercase tracking-widest">
          <div className="w-1.5 h-1.5 rounded-full bg-accent-green animate-pulse" />
          Awaiting_User_Input
        </div>
        
        <div className="grid grid-cols-2 sm:flex sm:items-center gap-3">
          {isUnread && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                onMarkRead(notification.id)
                onClose()
              }}
              className={cn(
                "h-10 sm:h-9 text-[10px] font-mono-data uppercase tracking-widest rounded-none",
                "border border-accent-green/40 bg-accent-green/5 text-accent-green hover:bg-accent-green hover:text-black transition-all"
              )}
            >
              <Check className="w-3.5 h-3.5 mr-2" /> Mark_Read
            </Button>
          )}
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              onDismiss(notification.id)
              onClose()
            }}
            className={cn(
              "h-10 sm:h-9 text-[10px] font-mono-data uppercase tracking-widest rounded-none",
              "border border-accent-red/40 bg-accent-red/5 text-accent-red hover:bg-accent-red hover:text-black transition-all",
              !isUnread && "col-span-2"
            )}
          >
            <Trash2 className="w-3.5 h-3.5 mr-2" /> Dismiss
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            className="sm:hidden h-10 text-[10px] font-mono-data uppercase tracking-widest rounded-none border border-border-dim col-span-2"
          >
            Close_Interface
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function MetaRow({ icon, label, value, className }: { icon: React.ReactNode; label: string; value: string; className?: string }) {
  return (
    <div className={cn(
      "flex items-center border-b border-border-dim last:border-b-0 p-2.5 gap-3 sm:odd:border-r sm:odd:border-b",
      className
    )}>
      <div className="flex items-center gap-1.5 min-w-[50px]">
        <span className="text-text-muted">{icon}</span>
        <span className="text-[8px] font-mono-data font-bold text-text-muted uppercase tracking-tighter">
          {label}
        </span>
      </div>
      <span className="text-[10px] font-mono-data text-text-primary truncate font-variant-numeric-tabular-nums">
        {value}
      </span>
    </div>
  )
}

