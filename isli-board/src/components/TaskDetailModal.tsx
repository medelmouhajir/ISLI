import { X, Hash, Calendar, User, Radio, Bot, Layers } from 'lucide-react'
import { Modal } from '@/components/ui/Modal'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'
import type { Agent, Task } from '@/types'

interface TaskDetailModalProps {
  open: boolean
  task: Task | null
  agents: Agent[]
  onClose: () => void
}

const priorityLabels: Record<number, string> = {
  1: 'CRIT',
  2: 'HIGH',
  3: 'NORM',
  4: 'LOW',
  5: 'MIN',
}

const statusVariants: Record<string, 'default' | 'success' | 'warning' | 'danger' | 'info' | 'muted'> = {
  pending: 'warning',
  pending_context: 'warning',
  inbox: 'default',
  doing: 'info',
  review: 'muted',
  done: 'success',
  failed: 'danger',
}

export function TaskDetailModal({ open, task, agents, onClose }: TaskDetailModalProps) {
  if (!task) return null

  const agent = agents.find((a) => a.id === task.agent_id)
  const priorityLabel = priorityLabels[task.priority] || `P${task.priority}`
  const statusVariant = statusVariants[task.status] || 'default'

  return (
    <Modal open={open} onClose={onClose} title="" className="max-w-xl">
      <div className="space-y-5">
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <h2 className="text-lg font-display font-semibold text-text-primary leading-tight">
              {task.title}
            </h2>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Badge variant={task.priority <= 2 ? 'danger' : task.priority === 3 ? 'info' : 'default'}>
                {priorityLabel}
              </Badge>
              <Badge variant={statusVariant}>
                {task.status}
              </Badge>
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            aria-label="Close dialog"
            className="rounded-full w-8 h-8 p-0 shrink-0"
          >
            <X className="w-4 h-4" />
          </Button>
        </div>

        {/* Metadata grid */}
        <div className="grid grid-cols-2 gap-3">
          <MetaItem icon={<Hash className="w-3 h-3" />} label="ID" value={task.id} />
          <MetaItem icon={<Calendar className="w-3 h-3" />} label="Created" value={formatDate(task.created_at)} />
          {task.scheduled_at && (
            <MetaItem icon={<Calendar className="w-3 h-3" />} label="Scheduled For" value={formatDate(task.scheduled_at)} />
          )}
          <MetaItem icon={<User className="w-3 h-3" />} label="Created By" value={task.created_by} />
          <MetaItem icon={<Radio className="w-3 h-3" />} label="Channel" value={task.channel || 'core'} />
          <MetaItem icon={<Bot className="w-3 h-3" />} label="Agent" value={agent?.name || task.agent_id || '—'} />
          <MetaItem icon={<Layers className="w-3 h-3" />} label="Depth" value={String(task.depth)} />
        </div>

        {/* Description */}
        {task.description && (
          <div className="border-t border-border-dim pt-4">
            <h3 className="text-[10px] font-display uppercase tracking-widest text-text-secondary mb-2">
              Description
            </h3>
            <p className="text-sm text-text-primary leading-relaxed">{task.description}</p>
          </div>
        )}

        {/* Input */}
        <div className="border-t border-border-dim pt-4">
          <h3 className="text-[10px] font-display uppercase tracking-widest text-text-secondary mb-2">
            Input
          </h3>
          <pre className="text-xs font-mono-data text-text-primary bg-bg-elevated border border-border-dim rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-words">
            {task.input || <span className="text-text-muted">—</span>}
          </pre>
        </div>

        {/* Output */}
        <div className="border-t border-border-dim pt-4">
          <h3 className="text-[10px] font-display uppercase tracking-widest text-text-secondary mb-2">
            Output
          </h3>
          {task.output ? (
            <pre className="text-xs font-mono-data text-text-primary bg-bg-elevated border border-border-dim rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-words">
              {task.output}
            </pre>
          ) : (
            <p className="text-sm text-text-muted">No output recorded</p>
          )}
        </div>

        {/* Tags */}
        {task.tags.length > 0 && (
          <div className="border-t border-border-dim pt-4">
            <h3 className="text-[10px] font-display uppercase tracking-widest text-text-secondary mb-2">
              Tags
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {task.tags.map((t) => (
                <span
                  key={t}
                  className="text-[10px] px-2 py-1 rounded bg-bg-elevated text-text-secondary border border-border-dim font-mono-data"
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}

function MetaItem({ icon, label, value }: { icon: React.ReactNode; label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-text-muted">{icon}</span>
      <div className="min-w-0">
        <span className="text-[10px] font-display uppercase tracking-wider text-text-muted block">{label}</span>
        <span className={cn('text-xs font-mono-data text-text-primary truncate block')}>{value}</span>
      </div>
    </div>
  )
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}
