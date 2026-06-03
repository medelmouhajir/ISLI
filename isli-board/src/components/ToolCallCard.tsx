import { Loader2, CheckCircle2, Wrench } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface ToolCallEvent {
  tool: string
  status: 'started' | 'done'
  result_summary?: string
  duration_ms?: number
}

export function ToolCallCard({ event }: { event: ToolCallEvent }) {
  const isDone = event.status === 'done'
  return (
    <div
      className={cn(
        'flex items-center gap-2 px-3 py-2 rounded-none border text-[11px] font-mono transition-all',
        isDone
          ? 'bg-accent-green/5 border-accent-green/20 text-accent-green'
          : 'bg-accent-amber/5 border-accent-amber/20 text-accent-amber'
      )}
    >
      {isDone ? (
        <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
      ) : (
        <Loader2 className="w-3.5 h-3.5 shrink-0 animate-spin" />
      )}
      <Wrench className="w-3.5 h-3.5 shrink-0 opacity-60" />
      <span className="font-bold truncate">{event.tool}</span>
      {isDone && event.duration_ms !== undefined && (
        <span className="ml-auto text-[10px] opacity-70 tabular-nums">
          {event.duration_ms.toFixed(0)}ms
        </span>
      )}
    </div>
  )
}

export function ToolCallBar({ events }: { events: ToolCallEvent[] }) {
  if (!events.length) return null
  return (
    <div className="flex flex-wrap gap-2 max-w-[80%] pl-11">
      {events.map((ev, i) => (
        <ToolCallCard key={`${ev.tool}-${i}`} event={ev} />
      ))}
    </div>
  )
}
