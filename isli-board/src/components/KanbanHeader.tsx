import { Search, Calendar, Plus } from 'lucide-react'
import { Select } from '@/components/ui/Select'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'

export type DateFilterType = 'today' | 'yesterday' | 'week' | 'month' | 'upcoming'

interface KanbanHeaderProps {
  searchQuery: string
  onSearchChange: (value: string) => void
  dateFilter: DateFilterType
  onDateFilterChange: (value: DateFilterType) => void
  onCreateTask?: () => void
}

export function KanbanHeader({
  searchQuery,
  onSearchChange,
  dateFilter,
  onDateFilterChange,
  onCreateTask,
}: KanbanHeaderProps) {
  return (
    <div className="px-4 py-3 bg-bg-base border-b border-border-dim flex flex-col md:flex-row gap-3 items-stretch md:items-center">
      {/* Create Task Button */}
      <Button
        onClick={onCreateTask}
        className="gap-2 px-5 font-mono text-[10px] font-bold uppercase tracking-[0.2em]"
      >
        <Plus className="w-3.5 h-3.5" strokeWidth={3} />
        Init_Task
      </Button>

      {/* Search Input */}
      <div className="relative flex-1 group">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted group-focus-within:text-accent-cyan transition-colors z-20" />
        <Input
          type="text"
          placeholder="Search all tasks..."
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          className="pl-9 font-mono text-sm"
        />
      </div>

      {/* Date Filter Dropdown */}
      <div className="relative min-w-[140px] group">
        <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted group-focus-within:text-accent-cyan transition-colors z-20 pointer-events-none" />
        <Select
          value={dateFilter}
          onChange={(e) => onDateFilterChange(e.target.value as DateFilterType)}
          className="pl-9 font-mono text-sm"
        >
          <option value="today">Today</option>
          <option value="upcoming">Upcoming</option>
          <option value="yesterday">Yesterday</option>
          <option value="week">This Week</option>
          <option value="month">This Month</option>
        </Select>
      </div>

      {/* Industrial Accent Folio */}
      <div className="hidden lg:flex items-center gap-2 pl-2 border-l border-border-dim">
        <span className="font-mono text-[10px] text-text-muted uppercase tracking-widest">
          Filter_Active
        </span>
        <div className="w-1.5 h-1.5 bg-accent-cyan animate-pulse" />
      </div>
    </div>
  )
}
