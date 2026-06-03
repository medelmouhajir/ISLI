import { useState } from 'react'
import { cn } from '@/lib/utils'
import { Terminal, ChevronDown, ChevronUp } from 'lucide-react'

export interface ProcessTraceEvent {
  event_type: string
  data: Record<string, unknown>
  timestamp: string
}

const EVENT_ICONS: Record<string, string> = {
  phase_start: '▸',
  phase_end: '◂',
  turn_start: '⟳',
  turn_end: '✓',
  cost_report: '$',
  tool_call: '🔧',
  error: '⚠',
  debug_prompt: '⌨',
  debug_response: '💬',
}

const EVENT_COLORS: Record<string, string> = {
  phase_start: 'text-accent-cyan',
  phase_end: 'text-accent-cyan',
  turn_start: 'text-accent-purple',
  turn_end: 'text-accent-purple',
  cost_report: 'text-accent-green',
  tool_call: 'text-accent-amber',
  error: 'text-red-400',
  debug_prompt: 'text-text-muted',
  debug_response: 'text-text-muted',
}

export function ProcessTracePane({ events }: { events: ProcessTraceEvent[] }) {
  const [expanded, setExpanded] = useState(false)
  if (!events.length) return null

  return (
    <div className="border-t border-border-dim bg-bg-surface">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-2 text-[10px] font-mono font-bold uppercase tracking-widest text-text-muted hover:text-text-primary transition-colors"
      >
        <div className="flex items-center gap-2">
          <Terminal className="w-3.5 h-3.5" />
          <span>Process Trace ({events.length} events)</span>
        </div>
        {expanded ? (
          <ChevronUp className="w-3.5 h-3.5" />
        ) : (
          <ChevronDown className="w-3.5 h-3.5" />
        )}
      </button>
      {expanded && (
        <div className="max-h-48 overflow-y-auto px-4 py-2 space-y-1 scrollbar-thin">
          {events.map((ev, i) => (
            <div key={i} className="flex items-start gap-2 text-[10px] font-mono">
              <span className={cn('shrink-0', EVENT_COLORS[ev.event_type] || 'text-text-muted')}>
                {EVENT_ICONS[ev.event_type] || '•'}
              </span>
              <span className="text-text-muted shrink-0">
                {new Date(ev.timestamp).toLocaleTimeString([], {
                  hour12: false,
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit',
                })}
              </span>
              <span className={cn('font-bold shrink-0', EVENT_COLORS[ev.event_type] || 'text-text-primary')}>
                {ev.event_type}
              </span>
              <span className="text-text-secondary truncate">
                {typeof ev.data.phase === 'string' && ev.data.phase}
                {typeof ev.data.tool === 'string' && ev.data.tool}
                {typeof ev.data.turn_number === 'number' && `turn ${ev.data.turn_number}`}
                {typeof ev.data.delta === 'string' && `${ev.data.delta.length} chars`}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
