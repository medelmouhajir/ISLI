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
  const isEmpty = tasks.length === 0

  return (
    <div
      className={cn(
        "flex flex-col h-full animate-stagger-in transition-all duration-300 ease-in-out shrink-0 select-none",
        isEmpty ? "w-full md:w-12" : "w-full md:w-80"
      )}
      style={{ animationDelay: `${index * 80}ms`, opacity: 0 }}
    >
      {/* Column Header */}
      <div className={cn(
        "flex items-center justify-between mb-3 px-1 shrink-0",
        isEmpty ? "md:hidden" : ""
      )}>
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

      {/* Scrollable Task List / Drop Zone */}
      <div
        ref={setNodeRef}
        className={cn(
          'flex-1 min-h-0 transition-colors duration-200 rounded-xl border',
          isEmpty
            ? 'flex flex-col items-center py-4 border-border-dim/50'
            : 'overflow-y-auto overflow-x-hidden space-y-2.5 pr-1 p-2 border-transparent',
          isOver
            ? 'bg-accent-cyan/10 border-accent-cyan/30 border-dashed'
            : (isEmpty ? 'bg-bg-surface/10' : 'bg-bg-base/50')
        )}
      >
        {!isEmpty ? (
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
        ) : (
          <>
            {/* Empty State - Mobile (Horizontal NO SIGNAL) */}
            <div className="md:hidden text-xs text-text-muted text-center py-10 border border-dashed border-border-dim rounded-lg bg-bg-surface/30 flex flex-col items-center gap-2 w-full">
              <span className="w-8 h-8 rounded-full bg-bg-elevated flex items-center justify-center">
                <svg className="w-4 h-4 text-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a2.25 2.25 0 0 0-2.25-2.25h-.75" />
                </svg>
              </span>
              <span className="font-mono-data">NO SIGNAL</span>
            </div>

            {/* Empty State - Desktop (Vertical Letters) */}
            <div className="hidden md:flex flex-col items-center flex-1 w-full justify-start select-none">
              <span className={cn('w-1.5 h-1.5 rounded-full mb-4 shrink-0', columnDotColors[status])} />
              <div className="flex flex-col items-center gap-1.5 py-1">
                {(columnLabels[status] || status).split('').map((char, i) => (
                  <span
                    key={i}
                    className={cn(
                      "text-[11px] leading-none font-mono-data font-bold uppercase tracking-normal",
                      columnColors[status] || 'text-text-secondary'
                    )}
                  >
                    {char}
                  </span>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
