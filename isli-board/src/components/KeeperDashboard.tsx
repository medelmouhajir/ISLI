import { useMemo, useRef, useState, useEffect } from 'react'
import { useKeeperDashboard } from '@/hooks/useKeeperDashboard'
import { useKeeperStream } from '@/hooks/useKeeperStream'
import { Badge } from '@/components/ui/Badge'
import { Modal } from '@/components/ui/Modal'
import type { KeeperInference } from '@/types'
import { cn } from '@/lib/utils'
import {
  BrainCircuit,
  Activity,
  Zap,
  AlertTriangle,
  Terminal,
  ChevronDown,
  ChevronUp,
  Server,
  Cpu,
  Settings,
} from 'lucide-react'

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}h ${m}m ${s}s`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / k ** i).toFixed(2))} ${sizes[i]}`
}

function getHealthVariant(status: string): 'success' | 'warning' | 'danger' {
  if (status === 'ready' || status === 'ok') return 'success'
  if (status === 'degraded') return 'warning'
  return 'danger'
}

function getErrorSeverity(error: string | null): 'danger' | 'warning' {
  if (!error) return 'warning'
  const low = error.toLowerCase()
  if (low.includes('timeout') || low.includes('connect') || low.includes('unreachable')) return 'danger'
  return 'warning'
}

export function KeeperDashboard() {
  const { data: dashboard, isLoading } = useKeeperDashboard()
  const { entries: streamEntries } = useKeeperStream()
  const [showPreviews, setShowPreviews] = useState(false)
  const [errorFilter, setErrorFilter] = useState('')
  const [selectedInference, setSelectedInference] = useState<KeeperInference | null>(null)
  const logRef = useRef<HTMLDivElement>(null)

  const liveInferences = useMemo(() => {
    if (streamEntries.length > 0) return streamEntries.slice().reverse()
    return dashboard?.recent_inferences?.slice().reverse() || []
  }, [streamEntries, dashboard?.recent_inferences])

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [liveInferences.length])

  const agentLadder = useMemo(() => {
    if (!dashboard?.stats?.agent_calls) return []
    const list = Object.entries(dashboard.stats.agent_calls).map(([agent_id, endpoints]) => {
      const total = Object.values(endpoints).reduce((a, b) => a + b, 0)
      return { agent_id, total, endpoints }
    })
    list.sort((a, b) => b.total - a.total)
    return list.slice(0, 10)
  }, [dashboard?.stats?.agent_calls])

  const maxAgentTotal = useMemo(() => {
    return Math.max(...agentLadder.map((a) => a.total), 1)
  }, [agentLadder])

  const errors = useMemo(() => {
    const base = dashboard?.recent_inferences?.filter((i) => i.status === 'error') || []
    const streamErrors = streamEntries.filter((i) => i.status === 'error')
    const merged = [...base, ...streamErrors]
    const seen = new Set<string>()
    const unique = merged.filter((i) => {
      const key = `${i.timestamp}-${i.agent_id}-${i.endpoint}-${i.error}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    if (errorFilter) {
      return unique.filter((i) =>
        (i.error || '').toLowerCase().includes(errorFilter.toLowerCase())
      )
    }
    return unique.slice(0, 20)
  }, [dashboard?.recent_inferences, streamEntries, errorFilter])

  const runningModels = useMemo(() => {
    const ps = dashboard?.health?.ollama_ps
    if (!ps || typeof ps !== 'object') return []
    const models = (ps as Record<string, unknown>).models
    if (!Array.isArray(models)) return []
    return models as Record<string, unknown>[]
  }, [dashboard?.health?.ollama_ps])

  if (isLoading || !dashboard) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-base h-full w-full min-h-0">
        <div className="flex flex-col items-center gap-3">
          <BrainCircuit className="w-8 h-8 text-accent-cyan animate-pulse" />
          <span className="text-xs text-text-muted font-mono-data">Loading Keeper telemetry...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto bg-bg-base h-full w-full min-h-0">
      <div className="p-4 space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-accent-cyan/10 border border-accent-cyan/20 flex items-center justify-center text-accent-cyan">
              <BrainCircuit className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-sm font-display font-bold text-text-primary uppercase tracking-wider">
                Keeper Dashboard
              </h1>
              <p className="text-[10px] text-text-muted font-mono-data">
                Live telemetry from the local Ollama sidecar
              </p>
            </div>
          </div>
          <Badge variant={getHealthVariant(dashboard.health.status)}>
            {dashboard.health.status.toUpperCase()}
          </Badge>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Identity Card */}
          <div className="bg-bg-surface border border-border-dim rounded-xl p-4 shadow-card lg:col-span-1">
            <div className="flex items-center gap-2 mb-3">
              <Cpu className="w-4 h-4 text-accent-cyan" />
              <span className="text-xs font-display font-bold uppercase tracking-widest text-text-primary">
                Core Identity
              </span>
            </div>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-text-muted">Backend</span>
                <Badge variant="info">{dashboard.identity.backend.toUpperCase()}</Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-text-muted">Gen Model</span>
                <span className="text-[11px] font-mono-data text-text-primary">
                  {dashboard.identity.default_gen_model}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-text-muted">Embed Model</span>
                <span className="text-[11px] font-mono-data text-text-primary">
                  {dashboard.identity.default_embed_model}
                </span>
              </div>
              <div className="h-px bg-border-dim my-2" />
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-text-muted">Parameters</span>
                  <span className="text-[11px] font-mono-data text-text-primary">
                    {dashboard.identity.model_info.parameter_size || '—'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-text-muted">Quantization</span>
                  <span className="text-[11px] font-mono-data text-text-primary">
                    {dashboard.identity.model_info.quantization || '—'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-text-muted">Context Length</span>
                  <span className="text-[11px] font-mono-data text-text-primary">
                    {dashboard.identity.model_info.context_length
                      ? `${dashboard.identity.model_info.context_length.toLocaleString()} tokens`
                      : '—'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-text-muted">Format</span>
                  <span className="text-[11px] font-mono-data text-text-primary">
                    {dashboard.identity.model_info.format || '—'}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Health Card */}
          <div className="bg-bg-surface border border-border-dim rounded-xl p-4 shadow-card lg:col-span-2">
            <div className="flex items-center gap-2 mb-3">
              <Activity className="w-4 h-4 text-accent-green" />
              <span className="text-xs font-display font-bold uppercase tracking-widest text-text-primary">
                Health & Status
              </span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="bg-bg-elevated border border-border-dim rounded-lg p-3">
                <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1">Status</div>
                <Badge variant={getHealthVariant(dashboard.health.status)}>
                  {dashboard.health.status.toUpperCase()}
                </Badge>
              </div>
              <div className="bg-bg-elevated border border-border-dim rounded-lg p-3">
                <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1">Uptime</div>
                <div className="text-sm font-mono-data text-text-primary">
                  {formatUptime(dashboard.health.uptime_seconds)}
                </div>
              </div>
              <div className="bg-bg-elevated border border-border-dim rounded-lg p-3">
                <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1">Active Requests</div>
                <div className="text-sm font-mono-data text-text-primary">
                  {dashboard.health.active_requests}
                </div>
              </div>
              <div className="bg-bg-elevated border border-border-dim rounded-lg p-3">
                <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1">Avg Latency</div>
                <div className="text-sm font-mono-data text-text-primary">
                  {dashboard.stats.avg_latency_ms.toFixed(0)} ms
                </div>
              </div>
            </div>
            <div className="mt-3">
              <div className="text-[10px] text-text-muted uppercase tracking-wider mb-2">Ollama Running Models</div>
              {runningModels.length === 0 ? (
                <div className="text-[11px] text-text-muted italic">No models currently loaded in VRAM</div>
              ) : (
                <div className="space-y-2">
                  {runningModels.map((m, i) => (
                    <div key={i} className="flex items-center justify-between bg-bg-elevated border border-border-dim rounded-lg px-3 py-2">
                      <div className="flex items-center gap-2">
                        <Server className="w-3.5 h-3.5 text-accent-cyan" />
                        <span className="text-[11px] font-mono-data text-text-primary">
                          {String(m.name || m.model || 'unknown')}
                        </span>
                      </div>
                      <span className="text-[10px] font-mono-data text-text-muted">
                        {typeof m.size_vram === 'number' ? formatBytes(Number(m.size_vram)) : '—'}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Live Inference Log */}
          <div className="bg-bg-surface border border-border-dim rounded-xl p-4 shadow-card lg:col-span-2 flex flex-col">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Terminal className="w-4 h-4 text-accent-purple" />
                <span className="text-xs font-display font-bold uppercase tracking-widest text-text-primary">
                  Live Inference Log
                </span>
                <span className="text-[10px] text-text-muted font-mono-data">({liveInferences.length})</span>
              </div>
              <button
                onClick={() => setShowPreviews((v) => !v)}
                className="flex items-center gap-1 text-[10px] text-text-muted hover:text-accent-cyan transition-colors"
              >
                {showPreviews ? (
                  <>
                    <ChevronUp className="w-3 h-3" />
                    Hide previews
                  </>
                ) : (
                  <>
                    <ChevronDown className="w-3 h-3" />
                    Show previews
                  </>
                )}
              </button>
            </div>
            <div
              ref={logRef}
              className="flex-1 overflow-y-auto max-h-96 space-y-1 pr-1 custom-scrollbar"
            >
              {liveInferences.length === 0 ? (
                <div className="text-center py-8 text-[11px] text-text-muted italic">
                  No inferences yet. Trigger an agent turn to see live data.
                </div>
              ) : (
                liveInferences.map((inf, i) => (
                  <div
                    key={i}
                    onClick={() => setSelectedInference(inf)}
                    className={cn(
                      'rounded-lg px-3 py-2 border text-[11px] space-y-1 transition-all cursor-pointer',
                      inf.status === 'error'
                        ? 'bg-accent-red/5 border-accent-red/20 hover:bg-accent-red/10'
                        : 'bg-bg-elevated border-border-dim hover:border-border-bright hover:bg-bg-elevated/80'
                    )}
                  >
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono-data text-text-muted">
                        {inf.timestamp ? new Date(inf.timestamp).toLocaleTimeString() : '—'}
                      </span>
                      <Badge variant="info">{inf.agent_id.slice(0, 12)}</Badge>
                      <Badge variant="muted">{inf.endpoint}</Badge>
                      <span className="font-mono-data text-text-muted">{inf.model}</span>
                      <span className={cn(
                        'font-mono-data ml-auto',
                        inf.latency_ms > 5000 ? 'text-accent-red' : inf.latency_ms > 1000 ? 'text-accent-amber' : 'text-accent-green'
                      )}>
                        {inf.latency_ms.toFixed(0)} ms
                      </span>
                    </div>
                    {showPreviews && (
                      <div className="text-[10px] text-text-secondary space-y-0.5">
                        <div className="truncate"><span className="text-text-muted">Prompt:</span> {inf.prompt_preview}</div>
                        {inf.completion_preview && (
                          <div className="truncate"><span className="text-text-muted">Out:</span> {inf.completion_preview}</div>
                        )}
                        {inf.error && (
                          <div className="text-accent-red truncate">{inf.error}</div>
                        )}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Agent Call Ladder */}
          <div className="bg-bg-surface border border-border-dim rounded-xl p-4 shadow-card lg:col-span-1">
            <div className="flex items-center gap-2 mb-3">
              <Zap className="w-4 h-4 text-accent-amber" />
              <span className="text-xs font-display font-bold uppercase tracking-widest text-text-primary">
                Agent Call Ladder
              </span>
            </div>
            {agentLadder.length === 0 ? (
              <div className="text-[11px] text-text-muted italic">No calls recorded yet.</div>
            ) : (
              <div className="space-y-2">
                {agentLadder.map((a) => (
                  <div key={a.agent_id} className="space-y-1">
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="font-mono-data text-text-primary truncate max-w-[70%]">
                        {a.agent_id.slice(0, 18)}
                      </span>
                      <span className="font-mono-data text-text-muted">{a.total}</span>
                    </div>
                    <div className="h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                      <div
                        className="h-full bg-accent-cyan rounded-full transition-all"
                        style={{ width: `${(a.total / maxAgentTotal) * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Error & Anomaly Feed */}
          <div className="bg-bg-surface border border-border-dim rounded-xl p-4 shadow-card lg:col-span-2">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-accent-red" />
                <span className="text-xs font-display font-bold uppercase tracking-widest text-text-primary">
                  Error & Anomaly Feed
                </span>
                <span className="text-[10px] text-text-muted font-mono-data">({errors.length})</span>
              </div>
              <input
                type="text"
                value={errorFilter}
                onChange={(e) => setErrorFilter(e.target.value)}
                placeholder="Filter errors..."
                className="bg-bg-elevated border border-border-dim rounded-lg px-2 py-1 text-[10px] text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-cyan w-40"
              />
            </div>
            <div className="space-y-1 max-h-64 overflow-y-auto pr-1 custom-scrollbar">
              {errors.length === 0 ? (
                <div className="text-center py-6 text-[11px] text-text-muted italic">No errors recorded.</div>
              ) : (
                errors.map((err, i) => (
                  <div
                    key={i}
                    onClick={() => setSelectedInference(err)}
                    className="flex items-start gap-2 bg-accent-red/5 border border-accent-red/10 rounded-lg px-3 py-2 cursor-pointer hover:bg-accent-red/10 transition-all"
                  >
                    <Badge variant={getErrorSeverity(err.error)}>
                      {getErrorSeverity(err.error) === 'danger' ? 'HIGH' : 'MED'}
                    </Badge>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 text-[10px] text-text-muted mb-0.5">
                        <span>{err.timestamp ? new Date(err.timestamp).toLocaleTimeString() : '—'}</span>
                        <span>·</span>
                        <span className="font-mono-data">{err.agent_id.slice(0, 12)}</span>
                        <span>·</span>
                        <span>{err.endpoint}</span>
                      </div>
                      <div className="text-[11px] text-accent-red truncate">{err.error}</div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Config Card */}
          <div className="bg-bg-surface border border-border-dim rounded-xl p-4 shadow-card lg:col-span-1">
            <div className="flex items-center gap-2 mb-3">
              <Settings className="w-4 h-4 text-text-muted" />
              <span className="text-xs font-display font-bold uppercase tracking-widest text-text-primary">
                Config Snapshot
              </span>
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-text-muted">num_ctx</span>
                <span className="text-[11px] font-mono-data text-text-primary">{dashboard.config.num_ctx}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-text-muted">num_batch</span>
                <span className="text-[11px] font-mono-data text-text-primary">{dashboard.config.num_batch}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-text-muted">Gen Model</span>
                <span className="text-[11px] font-mono-data text-text-primary truncate max-w-[50%]">
                  {dashboard.config.ollama_gen_model}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-text-muted">Embed Model</span>
                <span className="text-[11px] font-mono-data text-text-primary truncate max-w-[50%]">
                  {dashboard.config.ollama_embed_model}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <Modal
        open={!!selectedInference}
        onClose={() => setSelectedInference(null)}
        title="Inference Details"
        className="sm:max-w-2xl"
      >
        {selectedInference && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-bg-elevated border border-border-dim rounded-lg p-3">
                <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1">Agent ID</div>
                <div className="text-xs font-mono-data text-text-primary break-all">
                  {selectedInference.agent_id}
                </div>
              </div>
              <div className="bg-bg-elevated border border-border-dim rounded-lg p-3">
                <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1">Endpoint</div>
                <div className="text-xs font-mono-data text-text-primary">
                  {selectedInference.endpoint}
                </div>
              </div>
              <div className="bg-bg-elevated border border-border-dim rounded-lg p-3">
                <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1">Model</div>
                <div className="text-xs font-mono-data text-text-primary">
                  {selectedInference.model}
                </div>
              </div>
              <div className="bg-bg-elevated border border-border-dim rounded-lg p-3">
                <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1">Latency</div>
                <div className="text-xs font-mono-data text-text-primary">
                  {selectedInference.latency_ms.toFixed(2)} ms
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <div className="text-[10px] text-text-muted uppercase tracking-wider">Prompt / Input</div>
              <div className="bg-bg-elevated border border-border-dim rounded-lg p-3 max-h-48 overflow-y-auto custom-scrollbar">
                <pre className="text-[11px] text-text-primary whitespace-pre-wrap font-mono-data">
                  {selectedInference.prompt || selectedInference.prompt_preview || 'No input data'}
                </pre>
              </div>
            </div>

            <div className="space-y-2">
              <div className="text-[10px] text-text-muted uppercase tracking-wider">Completion / Output</div>
              <div className="bg-bg-elevated border border-border-dim rounded-lg p-3 max-h-64 overflow-y-auto custom-scrollbar">
                <pre className="text-[11px] text-text-primary whitespace-pre-wrap font-mono-data">
                  {selectedInference.completion || selectedInference.completion_preview || 'No output data'}
                </pre>
              </div>
            </div>

            {selectedInference.error && (
              <div className="space-y-2">
                <div className="text-[10px] text-accent-red uppercase tracking-wider font-bold">Error Trace</div>
                <div className="bg-accent-red/5 border border-accent-red/20 rounded-lg p-3">
                  <pre className="text-[11px] text-accent-red whitespace-pre-wrap font-mono-data">
                    {selectedInference.error}
                  </pre>
                </div>
              </div>
            )}

            <div className="flex items-center justify-between text-[10px] text-text-muted font-mono-data pt-2">
              <span>Tokens In: {selectedInference.tokens_in || '—'}</span>
              <span>Tokens Out: {selectedInference.tokens_out || '—'}</span>
              <span>{new Date(selectedInference.timestamp).toLocaleString()}</span>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
