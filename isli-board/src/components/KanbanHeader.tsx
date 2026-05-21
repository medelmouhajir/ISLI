import { Search, Calendar, ChevronDown, Plus } from 'lucide-react'
import { cn } from '@/lib/utils'

export type DateFilterType = 'today' | 'yesterday' | 'week' | 'month'

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
    <div className="px-4 py-3 bg-bg-base border-b border-border-base flex flex-col md:flex-row gap-3 items-stretch md:items-center">
      {/* Create Task Button - Industrial Anchor */}
      <button
        onClick={onCreateTask}
        className={cn(
          "h-[38px] px-5 flex items-center justify-center gap-2 transition-all duration-100 active:scale-[0.98]",
          "bg-black border border-[#00E676] rounded-none",
          "font-mono text-xs font-bold uppercase tracking-[0.2em] text-[#00E676]",
          "hover:bg-[#00E676] hover:text-black hover:shadow-[0_0_15px_rgba(0,230,118,0.3)]"
        )}
      >
        <Plus className="w-3.5 h-3.5" strokeWidth={3} />
        <span>Init_Task</span>
      </button>

      {/* Search Input */}
      <div className="relative flex-1 group">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted group-focus-within:text-accent-cyan transition-colors" />
        <input
          type="text"
          placeholder="Search all tasks..."
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          className={cn(
            "w-full bg-bg-surface border border-border-base pl-9 pr-3 py-1.5",
            "font-mono text-sm text-text-primary placeholder:text-text-muted",
            "focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan/20",
            "transition-all duration-200"
          )}
        />
      </div>

      {/* Date Filter Dropdown */}
      <div className="relative min-w-[140px]">
        <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted pointer-events-none" />
        <select
          value={dateFilter}
          onChange={(e) => onDateFilterChange(e.target.value as DateFilterType)}
          className={cn(
            "w-full appearance-none bg-bg-surface border border-border-base pl-9 pr-8 py-1.5",
            "font-mono text-sm text-text-primary cursor-pointer",
            "focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan/20",
            "transition-all duration-200"
          )}
        >
          <option value="today">Today</option>
          <option value="yesterday">Yesterday</option>
          <option value="week">This Week</option>
          <option value="month">This Month</option>
        </select>
        <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted pointer-events-none" />
      </div>

      {/* Industrial Accent Folio */}
      <div className="hidden lg:flex items-center gap-2 pl-2 border-l border-border-base">
        <span className="font-mono text-[10px] text-text-muted uppercase tracking-widest">
          Filter_Active
        </span>
        <div className="w-1.5 h-1.5 bg-accent-cyan animate-pulse" />
      </div>
    </div>
  )
}
