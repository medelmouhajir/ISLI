import { useMemo, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { 
  ChevronLeft, 
  Brain, 
  Database, 
  History, 
  AlertCircle, 
  ArrowRight,
  Search,
} from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { ConfirmationModal } from '@/components/ui/ConfirmationModal'
import { useAgents } from '@/hooks/useAgents'
import { useMemoryStream } from '@/hooks/useMemoryStream'
import { cn } from '@/lib/utils'
import * as diff from 'diff'

export function AgentMemoryPage() {
  const { id } = useParams<{ id: string }>()
  const { data: agents = [] } = useAgents()
  const agent = useMemo(() => agents.find((a) => a.id === id), [agents, id])
  const { events, setEvents } = useMemoryStream(id)
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

  const reversedEvents = useMemo(() => [...events].reverse(), [events])

  if (!agent) return null

  return (
    <div className="flex-1 flex flex-col bg-bg-base h-full w-full min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-border-dim bg-bg-surface shrink-0">
        <div className="flex items-center gap-4">
          <Link to={`/agents/${id}`}>
            <Button variant="ghost" size="sm" className="gap-2">
              <ChevronLeft className="w-4 h-4" />
              Back to Agent
            </Button>
          </Link>
          <div className="h-4 w-px bg-border-dim" />
          <div className="flex items-center gap-2">
            <Brain className="w-5 h-5 text-accent-cyan" />
            <h1 className="text-xl font-display font-bold text-text-primary">
              Memory Observability: {agent.name}
            </h1>
          </div>
        </div>
        <Button 
          variant="ghost" 
          size="sm" 
          onClick={() => setConfirmModal({
            open: true,
            title: 'Clear Observability History',
            description: 'Are you sure you want to clear the local memory event stream? This will only clear your current view and will not delete history from the server.',
            onConfirm: () => setEvents([]),
          })} 
          className="text-text-muted hover:text-accent-red"
        >
          Clear History
        </Button>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar">
        {reversedEvents.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-text-muted space-y-4 opacity-50">
            <Database className="w-16 h-16" />
            <p className="text-lg">Waiting for memory events...</p>
            <p className="text-sm">Trigger an agent turn to see journal updates and RAG signals.</p>
          </div>
        ) : (
          reversedEvents.map((event, idx) => (
            <div key={`${event.timestamp}-${idx}`} className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="h-px flex-1 bg-border-dim" />
                <span className="text-[10px] font-mono-data text-text-muted uppercase tracking-widest bg-bg-base px-2">
                  {new Date(event.timestamp).toLocaleString()}
                </span>
                <div className="h-px flex-1 bg-border-dim" />
              </div>

              {event.type === 'memory:journal_updated' && (
                <JournalUpdateCard payload={event.payload} />
              )}
              {event.type === 'memory:context_injected' && (
                <ContextInjectionCard payload={event.payload} />
              )}
              {event.type === 'memory:context_truncated' && (
                <TruncationWarningCard payload={event.payload} />
              )}
            </div>
          ))
        )}
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

function JournalUpdateCard({ payload }: { payload: any }) {
  const diffs = useMemo(() => {
    return diff.diffLines(payload.old_journal || '', payload.new_journal || '')
  }, [payload.old_journal, payload.new_journal])

  return (
    <div className="bg-bg-surface border border-border-dim rounded-xl overflow-hidden shadow-card">
      <div className="px-4 py-3 bg-accent-purple/5 border-b border-border-dim flex items-center justify-between">
        <div className="flex items-center gap-2">
          <History className="w-4 h-4 text-accent-purple" />
          <span className="text-xs font-display font-bold uppercase tracking-widest text-text-primary">
            Structured Journal Updated
          </span>
        </div>
        <Badge variant="info">Tier 2: Episodic Compaction</Badge>
      </div>
      <div className="p-4 bg-black/20 font-mono-data text-[11px] leading-relaxed max-h-[400px] overflow-y-auto custom-scrollbar">
        {diffs.map((part, i) => (
          <div
            key={i}
            className={cn(
              "whitespace-pre-wrap px-2",
              part.added ? "bg-accent-green/10 text-accent-green border-l-2 border-accent-green" :
              part.removed ? "bg-accent-red/10 text-accent-red border-l-2 border-accent-red line-through" :
              "text-text-secondary"
            )}
          >
            {part.value}
          </div>
        ))}
      </div>
    </div>
  )
}

function ContextInjectionCard({ payload }: { payload: any }) {
  return (
    <div className="bg-bg-surface border border-border-dim rounded-xl overflow-hidden shadow-card">
      <div className="px-4 py-3 bg-accent-cyan/5 border-b border-border-dim flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Search className="w-4 h-4 text-accent-cyan" />
          <span className="text-xs font-display font-bold uppercase tracking-widest text-text-primary">
            RAG Context Injected
          </span>
        </div>
        <div className="flex items-center gap-3">
           <div className="text-[10px] text-text-muted font-mono-data uppercase">
            Threshold: {(payload.threshold_used * 100).toFixed(0)}%
          </div>
          <Badge variant={payload.fallback_triggered ? 'warning' : 'success'}>
            {payload.fallback_triggered ? 'Fallback Triggered' : 'Healthy Retrieval'}
          </Badge>
        </div>
      </div>
      <div className="p-4 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-bg-elevated border border-border-dim rounded-lg p-3">
            <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1">Total Injected Tokens</div>
            <div className="text-lg font-mono-data text-text-primary">
              {payload.total_injected_tokens.toLocaleString()}
            </div>
          </div>
          <div className="bg-bg-elevated border border-border-dim rounded-lg p-3">
            <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1">Source Memories</div>
            <div className="text-lg font-mono-data text-text-primary">
              {payload.retrieved_memories.length}
            </div>
          </div>
        </div>

        <div className="space-y-2">
          <div className="text-[10px] text-text-muted uppercase tracking-wider font-bold">Retrieved Memory Fragments</div>
          <div className="space-y-2">
            {payload.retrieved_memories.map((mem: any, i: number) => (
              <div key={mem.id || i} className="bg-bg-elevated border border-border-dim rounded-lg p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <Badge variant="muted" className="text-[9px]">{mem.tier.toUpperCase()}</Badge>
                  <div className="flex items-center gap-1.5">
                    <div className="w-24 h-1.5 bg-black/20 rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-accent-cyan transition-all" 
                        style={{ width: `${mem.similarity_score * 100}%` }}
                      />
                    </div>
                    <span className="text-[10px] font-mono-data text-accent-cyan">
                      {(mem.similarity_score * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>
                <p className="text-[11px] text-text-secondary leading-relaxed">
                  {mem.content}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function TruncationWarningCard({ payload }: { payload: any }) {
  return (
    <div className="bg-accent-amber/5 border border-accent-amber/20 rounded-xl p-4 flex items-start gap-4 shadow-card">
      <div className="w-10 h-10 rounded-full bg-accent-amber/10 flex items-center justify-center text-accent-amber shrink-0">
        <AlertCircle className="w-6 h-6" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <span className="text-sm font-bold text-accent-amber uppercase tracking-wider">
            Context Truncated
          </span>
          <div className="flex items-center gap-2 text-[10px] font-mono-data text-accent-amber/70">
            <span>{payload.tokens_before.toLocaleString()}</span>
            <ArrowRight className="w-3 h-3" />
            <span className="font-bold">{payload.tokens_after.toLocaleString()}</span>
          </div>
        </div>
        <p className="text-xs text-text-primary leading-relaxed mb-2">
          {payload.warning_message}
        </p>
        <div className="flex gap-2">
          <Badge variant="warning" className="text-[9px]">F4 Mitigated</Badge>
          <Badge variant="warning" className="text-[9px]">History Pruned</Badge>
        </div>
      </div>
    </div>
  )
}
