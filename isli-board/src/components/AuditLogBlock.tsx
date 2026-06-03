import { useState } from 'react'
import { cn } from '@/lib/utils'
import { ChevronDown, ChevronRight, Activity, Cpu, Database, AlertCircle, Terminal } from 'lucide-react'

interface AuditLogBlockProps {
  log: {
    timestamp?: string
    level?: string
    event?: string
    tool?: string
    args?: any
    latency_ms?: number
    raw_output?: string
    error?: string
    errors?: any
    [key: string]: any
  }
}

export function AuditLogBlock({ log }: AuditLogBlockProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const isValidationFailure = log.event === 'runner.tool_validation_failed'
  
  return (
    <div className={cn(
      "my-2 border-l-2 font-mono-data transition-all duration-200 overflow-hidden rounded-r-md",
      isValidationFailure ? "border-[#FF3B30] bg-[#FF3B30]/5" : "border-[#C6FF4A] bg-[#C6FF4A]/5",
      isExpanded ? "max-h-[1000px]" : "max-h-12"
    )}>
      {/* Header / Summary Line */}
      <button 
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-white/5 transition-colors group"
      >
        <div className="flex-shrink-0 text-text-muted">
          {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </div>
        
        <div className="flex items-center gap-2">
          {isValidationFailure ? (
            <AlertCircle className="w-4 h-4 text-[#FF3B30]" />
          ) : (
            <Cpu className="w-4 h-4 text-[#C6FF4A]" />
          )}
          <span className={cn(
            "font-bold uppercase tracking-tighter text-sm",
            isValidationFailure ? "text-[#FF3B30]" : "text-[#C6FF4A]"
          )}>
            {isValidationFailure ? 'VALIDATION_REJECT' : 'TOOL_EXEC'}
          </span>
        </div>

        <div className="flex-1 truncate">
          <span className="text-text-primary font-bold mr-2">{log.tool}</span>
          {!isExpanded && (
            <span className="text-text-muted text-[10px] truncate">
              {log.args ? JSON.stringify(log.args) : log.error}
            </span>
          )}
        </div>

        {!isValidationFailure && log.latency_ms !== undefined && (
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded border border-[#C6FF4A]/20 bg-black/40">
            <Activity className="w-3 h-3 text-[#C6FF4A]" />
            <span className="text-[10px] tabular-nums text-[#C6FF4A]">{log.latency_ms}ms</span>
          </div>
        )}
      </button>

      {/* Expanded Audit Trace */}
      <div className="px-4 pb-4 pt-2 space-y-4 relative">
        {/* Structural Trace Pipe */}
        <div className="absolute left-6 top-0 bottom-4 w-px bg-white/10" />

        {/* 1. Arguments Block */}
        <div className="relative pl-8">
          <div className="absolute left-[-5px] top-1.5 w-2.5 h-2.5 rounded-full bg-white/20 border border-black" />
          <div className="flex items-center gap-2 mb-1">
            <Database className="w-3 h-3 text-text-muted" />
            <span className="text-[10px] uppercase tracking-widest text-text-muted font-bold">Inbound_Arguments</span>
          </div>
          <pre className="p-3 bg-black/60 border border-white/5 rounded text-[11px] text-text-primary overflow-x-auto">
            {JSON.stringify(log.args || {}, null, 2)}
          </pre>
        </div>

        {/* 2. Execution / Validation Details */}
        <div className="relative pl-8">
          <div className="absolute left-[-5px] top-1.5 w-2.5 h-2.5 rounded-full bg-white/20 border border-black" />
          <div className="flex items-center gap-2 mb-1">
            <Activity className="w-3 h-3 text-text-muted" />
            <span className="text-[10px] uppercase tracking-widest text-text-muted font-bold">
              {isValidationFailure ? 'Schema_Mismatches' : 'Execution_Telemetry'}
            </span>
          </div>
          <div className="p-3 bg-black/60 border border-white/5 rounded space-y-2">
            {isValidationFailure ? (
              <pre className="text-[11px] text-[#FF3B30] overflow-x-auto whitespace-pre-wrap">
                {JSON.stringify(log.errors || log.error, null, 2)}
              </pre>
            ) : (
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-text-muted">Process Latency</span>
                <span className="text-[#C6FF4A] tabular-nums font-bold">{log.latency_ms}ms</span>
              </div>
            )}
          </div>
        </div>

        {/* 3. Output Block */}
        {!isValidationFailure && (
          <div className="relative pl-8">
            <div className="absolute left-[-5px] top-1.5 w-2.5 h-2.5 rounded-full bg-[#C6FF4A] border border-black shadow-[0_0_8px_rgba(198,255,74,0.4)]" />
            <div className="flex items-center gap-2 mb-1">
              <Terminal className="w-3 h-3 text-text-muted" />
              <span className="text-[10px] uppercase tracking-widest text-text-muted font-bold">Outbound_Raw_Output</span>
            </div>
            <pre className="p-3 bg-black border border-[#C6FF4A]/20 rounded text-[11px] text-[#C6FF4A] overflow-x-auto whitespace-pre-wrap max-h-64">
              {log.raw_output || 'EMPTY_RESPONSE'}
            </pre>
          </div>
        )}
      </div>
    </div>
  )
}
