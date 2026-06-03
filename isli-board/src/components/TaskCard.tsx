import { forwardRef, useState } from 'react'
import { ArrowRight, XCircle, RotateCcw, GripVertical, Trash2, Eye, Calendar, Repeat } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { cn } from '@/lib/utils'
import type { Agent, Task } from '@/types'

interface TaskCardProps {
  task: Task
  onMove: (id: string, status: string) => void
  onDelete: (id: string) => void
  onShowDetail?: (task: Task) => void
  agents: Agent[]
  dragHandleProps?: React.HTMLAttributes<HTMLElement>
  isDragging?: boolean
  style?: React.CSSProperties
  dragOverlay?: boolean
}

const nextMap: Record<string, string> = {
  pending: 'inbox',
  inbox: 'doing',
  doing: 'review',
  review: 'done',
}

const priorityColors: Record<number, string> = {
  1: 'border-accent-red',
  2: 'border-accent-amber',
  3: 'border-accent-cyan',
  4: 'border-accent-green',
  5: 'border-accent-violet',
}

const priorityBg: Record<number, string> = {
  1: 'bg-accent-red/10 text-accent-red border-accent-red/20',
  2: 'bg-accent-amber/10 text-accent-amber border-accent-amber/20',
  3: 'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/20',
  4: 'bg-accent-green/10 text-accent-green border-accent-green/20',
  5: 'bg-accent-violet/10 text-accent-violet border-accent-violet/20',
}

const priorityLabels: Record<number, string> = {
  1: 'CRIT',
  2: 'HIGH',
  3: 'NORM',
  4: 'LOW',
  5: 'MIN',
}

export const TaskCard = forwardRef<HTMLDivElement, TaskCardProps>(
  function TaskCardInner({
    task,
    onMove,
    onDelete,
    onShowDetail,
    agents,
    dragHandleProps,
    isDragging,
    style,
    dragOverlay,
  }, ref) {
    const [showDelete, setShowDelete] = useState(false)
    const agent = agents.find((a) => a.id === task.agent_id)
    const priorityColor = priorityColors[task.priority] || 'border-border-dim'
    const priorityLabel = priorityLabels[task.priority] || `P${task.priority}`

    return (
      <div
        ref={ref}
        style={style}
        className={cn(
          'group relative bg-bg-surface rounded-xl p-3.5',
          'border border-border-dim border-l-[3px]',
          priorityColor,
          !dragOverlay && 'hover:border-border-bright hover:shadow-card-hover hover:-translate-y-0.5',
          isDragging && 'opacity-50',
          dragOverlay && 'shadow-xl rotate-1 scale-105 cursor-grabbing border-l-[3px]'
        )}
        onMouseEnter={() => setShowDelete(true)}
        onMouseLeave={() => setShowDelete(false)}
      >
        {/* Drag handle */}
        {dragHandleProps && (
          <button
            {...dragHandleProps}
            className="absolute left-1 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity p-0.5 rounded text-text-muted hover:text-text-secondary cursor-grab active:cursor-grabbing"
          >
            <GripVertical className="w-3 h-3" />
          </button>
        )}

        <div className={cn(dragHandleProps && 'pl-3')}>
          {/* Header */}
          <div className="flex items-start justify-between gap-2 mb-2">
            <h3 className="text-sm font-display font-medium text-text-primary leading-tight flex-1">
              {task.title}
            </h3>
            <div className="flex items-center gap-1 shrink-0">
              {onShowDetail && (
                <button
                  onClick={() => onShowDetail(task)}
                  className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded-md text-text-muted hover:text-accent-cyan hover:bg-accent-cyan/10"
                  aria-label="View task details"
                  title="View details"
                >
                  <Eye className="w-3.5 h-3.5" />
                </button>
              )}
              <Badge
                variant={task.priority <= 2 ? 'danger' : task.priority === 3 ? 'info' : 'default'}
                className={cn('text-[10px] px-1.5 py-0.5', priorityBg[task.priority])}
              >
                {priorityLabel}
              </Badge>
            </div>
          </div>

          {/* Description */}
          {task.description && (
            <p className="text-xs text-text-secondary mt-1.5 line-clamp-2 leading-relaxed">
              {task.description}
            </p>
          )}

          {/* Tags */}
          {task.tags.length > 0 && (
            <div className="mt-2.5 flex flex-wrap gap-1">
              {task.tags.map((t) => (
                <span
                  key={t}
                  className="text-[10px] px-2 py-0.5 rounded-full bg-bg-elevated text-text-secondary border border-border-dim font-mono-data"
                >
                  {t}
                </span>
              ))}
            </div>
          )}

          {/* Meta */}
          <div className="mt-2.5 flex items-center justify-between text-[11px] font-mono-data text-text-muted">
            <span className="text-text-secondary truncate max-w-[100px]">{agent ? agent.name : task.created_by}</span>
            <div className="flex items-center gap-1.5">
              {task.cron_expression && (
                <div className="flex items-center gap-1 text-accent-cyan" title={`Recurring: ${task.cron_expression}`}>
                  <Repeat className="w-3 h-3" />
                  <span>Cron</span>
                </div>
              )}
              {task.scheduled_at && (
                <div className="flex items-center gap-1 text-accent-amber" title="Scheduled">
                  <Calendar className="w-3 h-3" />
                  <span>{new Date(task.scheduled_at).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                </div>
              )}
              <span className="text-text-muted">{task.channel || 'core'}</span>
            </div>
          </div>

          {/* Actions */}
          <div className="mt-2.5 flex items-center gap-1.5 flex-wrap">
            {nextMap[task.status] && (
              <button
                onClick={() => onMove(task.id, nextMap[task.status])}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-accent-cyan/10 hover:bg-accent-cyan/20 text-accent-cyan text-[10px] font-mono-data font-semibold border border-accent-cyan/20 transition-colors"
              >
                <ArrowRight className="w-3 h-3" />
                {nextMap[task.status]}
              </button>
            )}

            <button
              onClick={() => onMove(task.id, 'failed')}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-accent-red/10 hover:bg-accent-red/20 text-accent-red text-[10px] font-mono-data font-semibold border border-accent-red/20 transition-colors"
            >
              <XCircle className="w-3 h-3" />
              fail
            </button>

            {task.status === 'failed' && (
              <button
                onClick={() => onMove(task.id, 'inbox')}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-bg-elevated hover:bg-border-dim text-text-secondary text-[10px] font-mono-data font-semibold border border-border-dim transition-colors"
              >
                <RotateCcw className="w-3 h-3" />
                retry
              </button>
            )}

            {showDelete && (
              <button
                onClick={() => onDelete(task.id)}
                className="ml-auto inline-flex items-center gap-1 px-2 py-1 rounded-md bg-accent-red/10 hover:bg-accent-red/20 text-accent-red text-[10px] font-mono-data font-semibold border border-accent-red/20 transition-colors opacity-0 group-hover:opacity-100"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }
)

TaskCard.displayName = 'TaskCard'
