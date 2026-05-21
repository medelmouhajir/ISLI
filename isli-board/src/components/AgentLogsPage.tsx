import { useState, useEffect, useRef, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ChevronLeft, Terminal, Trash2, Download, Search, Settings2 } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { useAgents } from '@/hooks/useAgents'
import { cn } from '@/lib/utils'

interface LogEntry {
  timestamp?: string
  level?: string
  event?: string
  [key: string]: any
}

export function AgentLogsPage() {
  const { id } = useParams<{ id: string }>()
  const { data: agents = [] } = useAgents()
  const agent = useMemo(() => agents.find((a) => a.id === id), [agents, id])

  const [logs, setLogs] = useState<LogEntry[]>([])
  const [filter, setFilter] = useState('')
  const [autoScroll, setAutoScroll] = useState(true)
  const [isConnected, setIsConnected] = useState(false)
  
  const scrollRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (!id) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const wsUrl = `${protocol}//${host}/api/v1/agents/${id}/logs/stream`

    const connect = () => {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        setIsConnected(true)
        console.log('Logs WebSocket connected')
      }

      ws.onmessage = (event) => {
        try {
          const entry = JSON.parse(event.data)
          setLogs((prev) => [...prev, entry].slice(-1000)) // Keep last 1000 logs
        } catch (e) {
          console.error('Failed to parse log entry:', e)
        }
      }

      ws.onclose = () => {
        setIsConnected(false)
        console.log('Logs WebSocket disconnected')
        // Reconnect after 3 seconds
        setTimeout(connect, 3000)
      }

      ws.onerror = (error) => {
        console.error('Logs WebSocket error:', error)
        ws.close()
      }
    }

    connect()

    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [id])

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  const filteredLogs = useMemo(() => {
    if (!filter) return logs
    const lowerFilter = filter.toLowerCase()
    return logs.filter((log) => 
      JSON.stringify(log).toLowerCase().includes(lowerFilter)
    )
  }, [logs, filter])

  const downloadLogs = () => {
    const blob = new Blob([JSON.stringify(logs, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `agent-${id}-logs-${new Date().toISOString()}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const clearLogs = () => {
    setLogs([])
  }

  return (
    <div className="flex-1 flex flex-col h-full bg-bg-base overflow-hidden">
      {/* Header */}
      <div className="p-4 md:p-6 border-b border-border-dim flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex flex-col gap-2">
          <Link 
            to={`/agents/${id}`}
            className="flex items-center gap-2 text-xs font-display font-bold uppercase tracking-widest text-text-muted hover:text-accent-cyan transition-colors w-fit"
          >
            <ChevronLeft className="w-4 h-4" />
            Back to Agent Detail
          </Link>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-bg-surface border border-border-dim flex items-center justify-center text-accent-cyan shadow-sm">
              <Terminal className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-xl font-display font-bold text-text-primary">Live Logs: {agent?.name || id}</h1>
              <div className="flex items-center gap-2 mt-0.5">
                <div className={cn("w-1.5 h-1.5 rounded-full", isConnected ? "bg-accent-green animate-pulse" : "bg-accent-red")} />
                <span className="text-[10px] font-mono-data text-text-muted uppercase tracking-wider">
                  {isConnected ? 'Live Stream Active' : 'Connecting...'}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
            <Input 
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter logs..."
              className="pl-10 h-9 w-48 md:w-64 bg-bg-surface border-border-dim"
            />
          </div>
          <Button variant="ghost" size="sm" onClick={clearLogs} title="Clear logs">
            <Trash2 className="w-4 h-4" />
          </Button>
          <Button variant="ghost" size="sm" onClick={downloadLogs} title="Download logs">
            <Download className="w-4 h-4" />
          </Button>
          <div className="h-6 w-px bg-border-dim mx-1" />
          <Button 
            variant="ghost" 
            size="sm" 
            onClick={() => setAutoScroll(!autoScroll)}
            className={cn(autoScroll ? "text-accent-cyan" : "text-text-muted")}
          >
            {autoScroll ? <Settings2 className="w-4 h-4 mr-2 animate-spin-slow" /> : <Settings2 className="w-4 h-4 mr-2" />}
            Auto-scroll
          </Button>
        </div>
      </div>

      {/* Terminal View */}
      <div className="flex-1 overflow-hidden p-4 md:p-6 bg-bg-base">
        <div 
          ref={scrollRef}
          className="h-full w-full bg-[#0d1117] border border-border-dim rounded-2xl overflow-y-auto font-mono-data text-xs p-4 shadow-inner"
        >
          {filteredLogs.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-text-muted space-y-3 opacity-50">
              <Terminal className="w-12 h-12" />
              <p>No log entries found. Waiting for agent activity...</p>
            </div>
          ) : (
            <div className="space-y-1">
              {filteredLogs.map((log, i) => (
                <div key={i} className="group flex gap-3 py-0.5 hover:bg-white/5 px-2 rounded -mx-2 transition-colors">
                  <span className="text-text-muted flex-shrink-0 w-32 select-none">
                    {log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : '---'}
                  </span>
                  <span className={cn(
                    "flex-shrink-0 w-16 font-bold uppercase select-none",
                    log.level === 'error' ? 'text-accent-red' : 
                    log.level === 'warning' ? 'text-accent-amber' : 
                    log.level === 'debug' ? 'text-text-muted' : 
                    'text-accent-cyan'
                  )}>
                    {log.level || 'info'}
                  </span>
                  <div className="flex-1 flex flex-col">
                    <span className="text-text-primary">
                      <span className="text-accent-purple font-bold mr-2">{log.event}:</span>
                      {Object.entries(log)
                        .filter(([k]) => !['timestamp', 'level', 'event'].includes(k))
                        .map(([k, v]) => (
                          <span key={k} className="mr-3">
                            <span className="text-text-muted">{k}=</span>
                            <span className="text-accent-amber">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>
                          </span>
                        ))
                      }
                    </span>
                  </div>
                </div>
              ))}
              <div className="h-4" /> {/* Spacer for bottom */}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
