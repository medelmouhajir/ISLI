import { useDroppable } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { SortableTaskCard } from './SortableTaskCard'
import type { Agent, Task } from '@/types'
import { cn } from '@/lib/utils'

interface KanbanColumnProps {
  status: string
  tasks: Task[]
  onMove: (id: string, status: string) => void
  onDelete: (id: string) => void
  onShowDetail?: (task: Task) => void
  agents: Agent[]
  index: number
}

const columnLabels: Record<string, string> = {
  pending: 'Scheduled',
  pending_context: 'Pending',
  inbox: 'Inbox',
  doing: 'Doing',
  review: 'Review',
  done: 'Done',
  failed: 'Failed',
}

const columnColors: Record<string, string> = {
  pending: 'text-accent-amber',
  pending_context: 'text-accent-amber',
  inbox: 'text-text-secondary',
  doing: 'text-accent-cyan',
  review: 'text-accent-violet',
  done: 'text-accent-green',
  failed: 'text-accent-red',
}

const columnDotColors: Record<string, string> = {
  pending: 'bg-accent-amber',
  pending_context: 'bg-accent-amber',
  inbox: 'bg-text-muted',
  doing: 'bg-accent-cyan',
  review: 'bg-accent-violet',
  done: 'bg-accent-green',
  failed: 'bg-accent-red',
}

export function KanbanColumn({ status, tasks, onMove, onDelete, onShowDetail, agents, index }: KanbanColumnProps) {
  const { setNodeRef, isOver } = useDroppable({ id: status })

  return (
    <div
      className="w-80 flex flex-col h-full animate-stagger-in"
      style={{ animationDelay: `${index * 80}ms`, opacity: 0 }}
    >
      {/* Column Header */}
      <div className="flex items-center justify-between mb-3 px-1 shrink-0">
        <div className="flex items-center gap-2">
          <span className={cn('w-2 h-2 rounded-full', columnDotColors[status])} />
          <h2 className={cn(
            'text-xs font-display font-semibold uppercase tracking-widest',
            columnColors[status] || 'text-text-secondary'
          )}>
            {columnLabels[status] || status}
          </h2>
        </div>
        <span className={cn(
          'text-[11px] px-2 py-0.5 rounded-full font-mono-data font-semibold border transition-colors',
          isOver
            ? 'border-accent-cyan text-accent-cyan bg-accent-cyan/10'
            : 'border-border-dim text-text-muted bg-bg-elevated'
        )}>
          {tasks.length}
        </span>
      </div>

      {/* Scrollable Task List */}
      <div
        ref={setNodeRef}
        className={cn(
          'flex-1 min-h-0 overflow-y-auto overflow-x-hidden space-y-2.5 pr-1 rounded-xl transition-colors duration-200',
          'p-2',
          isOver ? 'bg-accent-cyan/5 border border-accent-cyan/20 border-dashed' : 'bg-bg-base/50'
        )}
      >
        <SortableContext items={tasks.map((t) => t.id)} strategy={verticalListSortingStrategy}>
          {tasks.map((task) => (
            <SortableTaskCard
              key={task.id}
              task={task}
              onMove={onMove}
              onDelete={onDelete}
              onShowDetail={onShowDetail}
              agents={agents}
            />
          ))}
        </SortableContext>

        {tasks.length === 0 && (
          <div className="text-xs text-text-muted text-center py-10 border border-dashed border-border-dim rounded-lg bg-bg-surface/30 flex flex-col items-center gap-2">
            <span className="w-8 h-8 rounded-full bg-bg-elevated flex items-center justify-center">
              <svg className="w-4 h-4 text-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a2.25 2.25 0 0 0-2.25-2.25h-.75" />
              </svg>
            </span>
            <span className="font-mono-data">NO SIGNAL</span>
          </div>
        )}
      </div>
    </div>
  )
}
