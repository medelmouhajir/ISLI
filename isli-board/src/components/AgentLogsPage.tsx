import { useState, useEffect, useRef, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ChevronLeft, Terminal, Trash2, Download, Search, Settings2, ShieldAlert, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { ConfirmationModal } from '@/components/ui/ConfirmationModal'
import { useAgents } from '@/hooks/useAgents'
import { cn } from '@/lib/utils'
import { AuditLogBlock } from './AuditLogBlock'

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
  const isHistoryLoadedRef = useRef(false)
  const pendingLogsRef = useRef<LogEntry[]>([])
  const [filter, setFilter] = useState('')
  const [autoScroll, setAutoScroll] = useState(true)
  const [isConnected, setIsConnected] = useState(false)
  
  const [historyOffset, setHistoryOffset] = useState(100)
  const [hasMoreHistory, setHasMoreHistory] = useState(true)
  const [isLoadingHistory, setIsLoadingHistory] = useState(false)
  const [confirmModal, setConfirmModal] = useState<{
    open: boolean;
    title: string;
    description: string;
    onConfirm: () => void | Promise<void>;
  }>({
    open: false,
    title: '',
    description: '',
    onConfirm: () => {},
  })

  const scrollRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)

  const loadOlderHistory = async () => {
    if (!id || isLoadingHistory || !hasMoreHistory) return
    
    setIsLoadingHistory(true)
    const container = scrollRef.current
    const prevScrollHeight = container?.scrollHeight || 0
    
    try {
      const res = await fetch(`/api/v1/agents/${id}/logs/history?limit=100&offset=${historyOffset}`)
      const olderLogs = await res.json()
      
      if (Array.isArray(olderLogs)) {
        if (olderLogs.length < 100) {
          setHasMoreHistory(false)
        }
        
        // Dedup against existing logs
        const existingKeys = new Set(logs.map(l => `${l.timestamp}-${l.event}-${JSON.stringify(l.args || {})}`))
        const filteredOlder = olderLogs.filter(l => !existingKeys.has(`${l.timestamp}-${l.event}-${JSON.stringify(l.args || {})}`))
        
        if (filteredOlder.length > 0) {
          setLogs(prev => [...filteredOlder, ...prev])
          setHistoryOffset(prev => prev + 100)
          
          // Anchor scroll position
          requestAnimationFrame(() => {
            if (container) {
              container.scrollTop += container.scrollHeight - prevScrollHeight
            }
          })
        } else if (olderLogs.length > 0) {
          // All were duplicates but we got some, try next page
          setHistoryOffset(prev => prev + 100)
        }
      }
    } catch (err) {
      console.error('Failed to load older history:', err)
    } finally {
      setIsLoadingHistory(false)
    }
  }

  useEffect(() => {
    if (!id) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const wsUrl = `${protocol}//${host}/api/v1/agents/${id}/logs/stream`

    // 1. Start WebSocket and buffer incoming events
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
          if (!isHistoryLoadedRef.current) {
            pendingLogsRef.current.push(entry)
          } else {
            setLogs((prev) => [...prev, entry].slice(-1000))
          }
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

    // 2. Fetch history and flush buffer
    fetch(`/api/v1/agents/${id}/logs/history?limit=100`)
      .then((res) => res.json())
      .then((history) => {
        if (Array.isArray(history)) {
          setLogs([...history, ...pendingLogsRef.current].slice(-1000))
        }
        isHistoryLoadedRef.current = true
        pendingLogsRef.current = []
      })
      .catch((err) => {
        console.error('Failed to fetch log history:', err)
        isHistoryLoadedRef.current = true // Allow live logs to start flowing anyway
      })

    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
      isHistoryLoadedRef.current = false
      pendingLogsRef.current = []
      setHistoryOffset(100)
      setHasMoreHistory(true)
      setIsLoadingHistory(false)
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
    setConfirmModal({
      open: true,
      title: 'Clear Session Logs',
      description: 'Are you sure you want to clear the logs in the current view? This will only clear your local terminal view and will not delete history from the server.',
      onConfirm: () => setLogs([]),
    })
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
              <div className="flex flex-col items-center py-4 border-b border-white/5 mb-4">
                {hasMoreHistory ? (
                  <Button 
                    variant="ghost" 
                    size="sm" 
                    onClick={loadOlderHistory} 
                    disabled={isLoadingHistory}
                    className="text-[10px] font-mono-data uppercase tracking-widest text-accent-cyan hover:bg-accent-cyan/10"
                  >
                    {isLoadingHistory ? 'Synchronizing History...' : 'Load Older Logs'}
                  </Button>
                ) : (
                  <span className="text-[10px] font-mono-data uppercase tracking-widest text-text-muted opacity-50">
                    Showing oldest available logs (1000 max)
                  </span>
                )}
              </div>

              {filteredLogs.map((log, i) => {
                // 1. Audit Logs (Industrial Anchor)
                if (log.event === 'runner.tool_execution' || log.event === 'runner.tool_validation_failed') {
                  return <AuditLogBlock key={i} log={log} />
                }

                // 2. Circuit Breaker Transitions (Industrial Signaling)
                if (log.event === 'circuit_breaker.transition') {
                  const stateColor = 
                    log.state === 'OPEN' ? 'text-[#FF3B30]' : 
                    log.state === 'HALF_OPEN' ? 'text-[#FFB800]' : 
                    'text-[#C6FF4A]'
                  
                  return (
                    <div key={i} className={cn("flex gap-3 py-1 px-2 rounded -mx-2 bg-white/5 border border-white/10 my-1")}>
                      <span className="text-text-muted flex-shrink-0 w-32 select-none">
                        {log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : '---'}
                      </span>
                      <div className="flex-1 flex items-center gap-2">
                        {log.state === 'OPEN' ? <ShieldAlert className={cn("w-4 h-4", stateColor)} /> : <ShieldCheck className={cn("w-4 h-4", stateColor)} />}
                        <span className="text-text-primary font-bold">
                          CIRCUIT_BREAKER: <span className={cn("uppercase", stateColor)}>{log.name}</span> TRANSITIONED TO <span className={cn("font-black underline", stateColor)}>{log.state}</span>
                        </span>
                      </div>
                    </div>
                  )
                }

                // 3. Standard Logs
                return (
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
                )
              })}
              <div className="h-4" /> {/* Spacer for bottom */}
            </div>
          )}
        </div>
      </div>
      <ConfirmationModal
        open={confirmModal.open}
        title={confirmModal.title}
        description={confirmModal.description}
        variant="warning"
        confirmText="Clear View"
        onConfirm={confirmModal.onConfirm}
        onClose={() => setConfirmModal(prev => ({ ...prev, open: false }))}
      />
    </div>
  )
}
