import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { TaskCard } from './TaskCard'
import type { Agent, Task } from '@/types'

interface SortableTaskCardProps {
  task: Task
  onMove: (id: string, status: string) => void
  onDelete: (id: string) => void
  onShowDetail?: (task: Task) => void
  agents: Agent[]
}

export function SortableTaskCard({ task, onMove, onDelete, onShowDetail, agents }: SortableTaskCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: task.id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  return (
    <TaskCard
      ref={setNodeRef}
      task={task}
      onMove={onMove}
      onDelete={onDelete}
      onShowDetail={onShowDetail}
      agents={agents}
      dragHandleProps={{ ...attributes, ...listeners }}
      isDragging={isDragging}
      style={style}
    />
  )
}
