import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  KeyboardSensor,
  closestCorners,
  useSensors,
  useSensor,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import { sortableKeyboardCoordinates } from '@dnd-kit/sortable'
import { motion, AnimatePresence } from 'framer-motion'
import {
  startOfDay,
  endOfDay,
  subDays,
  startOfWeek,
  startOfMonth,
  isWithinInterval,
  parseISO,
} from 'date-fns'
import { KanbanColumn } from './KanbanColumn'
import { TaskCard } from './TaskCard'
import { ScheduleTaskModal } from './ScheduleTaskModal'
import { KanbanHeader, type DateFilterType } from './KanbanHeader'
import { CreateTaskModal } from './CreateTaskModal'
import { COLUMNS } from '@/lib/constants'
import type { Agent, Task } from '@/types'
import { cn } from '@/lib/utils'

interface KanbanBoardProps {
  tasks: Task[]
  onMove: (id: string, status: string) => void
  onSchedule: (id: string, date: string) => void
  onDelete: (id: string) => void
  onShowDetail?: (task: Task) => void
  agents: Agent[]
  onAuthRequired?: () => void
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

export function KanbanBoard({ tasks, onMove, onSchedule, onDelete, onShowDetail, agents, onAuthRequired }: KanbanBoardProps) {
  const [activeId, setActiveId] = useState<string | null>(null)
  const [schedulingTaskId, setSchedulingTaskId] = useState<string | null>(null)
  const [showTaskModal, setShowTaskModal] = useState(false)
  const [mobileColumn, setMobileColumn] = useState<string>('inbox')
  const [searchQuery, setSearchQuery] = useState('')
  const [dateFilter, setDateFilter] = useState<DateFilterType>('today')
  
  const [items, setItems] = useState<Record<string, string[]>>(() => {
    const initial: Record<string, string[]> = {}
    COLUMNS.forEach((col) => {
      initial[col] = tasks.filter((t) => t.status === col).map((t) => t.id)
    })
    return initial
  })

  const filteredTasks = useMemo(() => {
    const now = new Date()
    return tasks.filter((t) => {
      // 1. Search filter
      const matchesSearch =
        t.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (t.description?.toLowerCase().includes(searchQuery.toLowerCase()) ?? false)

      if (!matchesSearch) return false

      // 2. Date filter
      const taskDateStr = t.scheduled_at || t.created_at
      if (!taskDateStr) return true // Should not happen based on types, but safety first
      const taskDate = parseISO(taskDateStr)

      switch (dateFilter) {
        case 'today':
          return isWithinInterval(taskDate, {
            start: startOfDay(now),
            end: endOfDay(now),
          })
        case 'yesterday': {
          const yesterday = subDays(now, 1)
          return isWithinInterval(taskDate, {
            start: startOfDay(yesterday),
            end: endOfDay(yesterday),
          })
        }
        case 'week':
          return taskDate >= startOfWeek(now, { weekStartsOn: 1 }) // Monday start
        case 'month':
          return taskDate >= startOfMonth(now)
        case 'upcoming':
          return taskDate > now
        default:
          return true
      }
    })
  }, [tasks, searchQuery, dateFilter])

  useEffect(() => {
    const next: Record<string, string[]> = {}
    COLUMNS.forEach((col) => {
      next[col] = filteredTasks.filter((t) => t.status === col).map((t) => t.id)
    })
    setItems(next)
  }, [filteredTasks])

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 8 },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  )

  const findContainer = useCallback(
    (id: string) => {
      if ((COLUMNS as readonly string[]).includes(id)) return id
      return COLUMNS.find((col) => items[col]?.includes(id))
    },
    [items]
  )

  const handleDragStart = useCallback((event: DragStartEvent) => {
    setActiveId(event.active.id as string)
  }, [])

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event
      setActiveId(null)

      if (!over) return

      const activeId = active.id as string
      const overId = over.id as string

      const activeContainer = findContainer(activeId)
      const overContainer = findContainer(overId)

      if (!activeContainer || !overContainer) return
      if (activeContainer === overContainer) return

      if (overContainer === 'pending') {
        setSchedulingTaskId(activeId)
        return
      }

      onMove(activeId, overContainer)

      setItems((prev) => {
        const next = { ...prev }
        next[activeContainer] = next[activeContainer].filter((id) => id !== activeId)
        next[overContainer] = [...next[overContainer], activeId]
        return next
      })
    },
    [findContainer, onMove]
  )

  const activeTask = activeId ? tasks.find((t) => t.id === activeId) : null

  const mobileColumnTasks = useMemo(() => {
    return filteredTasks.filter((t) => t.status === mobileColumn)
  }, [filteredTasks, mobileColumn])

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <div className="flex-1 flex flex-col min-h-0 min-w-0 relative z-10">
        <KanbanHeader
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          dateFilter={dateFilter}
          onDateFilterChange={setDateFilter}
          onCreateTask={() => setShowTaskModal(true)}
        />

        {/* Mobile Column Tabs */}
        <div className="md:hidden px-4 pt-3 pb-2 overflow-x-auto shrink-0">
          <div className="flex gap-1.5 min-w-max">
            {COLUMNS.map((col) => {
              const count = filteredTasks.filter((t) => t.status === col).length
              return (
                <button
                  key={col}
                  onClick={() => setMobileColumn(col)}
                  className={cn(
                    'relative px-3 py-1.5 rounded-lg text-xs font-display font-semibold transition-all duration-200 border',
                    mobileColumn === col
                      ? 'bg-bg-elevated border-border-bright text-text-primary shadow-card'
                      : 'bg-transparent border-transparent text-text-muted hover:text-text-secondary hover:bg-bg-surface'
                  )}
                >
                  <span className={cn('mr-1.5', columnColors[col])}>●</span>
                  {columnLabels[col]}
                  <span className="ml-1.5 text-[10px] font-mono-data text-text-muted">
                    {count}
                  </span>
                </button>
              )
            })}
          </div>
        </div>

        {/* Desktop: horizontal scroll columns */}
        <div className="hidden md:flex flex-1 overflow-x-auto overflow-y-hidden">
          <div className="flex gap-4 h-full p-4 min-w-max">
            {COLUMNS.map((col, index) => {
              const colTasks = filteredTasks.filter((t) => t.status === col)
              return (
                <KanbanColumn
                  key={col}
                  status={col}
                  tasks={colTasks}
                  onMove={onMove}
                  onDelete={onDelete}
                  onShowDetail={onShowDetail}
                  agents={agents}
                  index={index}
                />
              )
            })}
          </div>
        </div>

        {/* Mobile: single column view */}
        <div className="md:hidden flex-1 overflow-y-auto px-4 py-2">
          <AnimatePresence mode="wait">
            <motion.div
              key={mobileColumn}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.2 }}
              className="h-full"
            >
              <KanbanColumn
                status={mobileColumn}
                tasks={mobileColumnTasks}
                onMove={onMove}
                onDelete={onDelete}
                onShowDetail={onShowDetail}
                agents={agents}
                index={0}
              />
            </motion.div>
          </AnimatePresence>
        </div>
      </div>


      <DragOverlay dropAnimation={null}>
        {activeTask ? (
          <TaskCard
            task={activeTask}
            onMove={onMove}
            onDelete={onDelete}
            agents={agents}
            dragOverlay
          />
        ) : null}
      </DragOverlay>

      <ScheduleTaskModal
        open={!!schedulingTaskId}
        onClose={() => setSchedulingTaskId(null)}
        onSubmit={(date) => {
          if (schedulingTaskId) {
            onSchedule(schedulingTaskId, date)
            setSchedulingTaskId(null)
          }
        }}
        taskTitle={tasks.find((t) => t.id === schedulingTaskId)?.title}
      />

      <CreateTaskModal
        open={showTaskModal}
        onClose={() => setShowTaskModal(false)}
        agents={agents}
        onAuthRequired={onAuthRequired}
      />
    </DndContext>
  )
}
