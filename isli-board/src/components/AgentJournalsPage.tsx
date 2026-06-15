import { useState, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { 
  ChevronLeft, 
  BookOpen, 
  RefreshCw, 
  Trash2, 
  Edit3,
  Calendar,
  MessageSquare,
  AlertCircle,
} from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Modal } from '@/components/ui/Modal'
import { Textarea } from '@/components/ui/Textarea'
import { ConfirmationModal } from '@/components/ui/ConfirmationModal'
import { useAgents } from '@/hooks/useAgents'
import { getJSON, putJSON, postJSON, deleteJSON } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { Session } from '@/types'

export function AgentJournalsPage() {
  const { id } = useParams<{ id: string }>()
  const { data: agents = [] } = useAgents()
  const agent = useMemo(() => agents.find((a) => a.id === id), [agents, id])

  const { data: sessions = [], isLoading, refetch } = useQuery({
    queryKey: ['agent-sessions', id],
    queryFn: () => getJSON<Session[]>(`/v1/sessions?agent_id=${id}&include_closed=true`),
    enabled: !!id,
  })

  const [editingSession, setEditingSession] = useState<Session | null>(null)
  const [editValue, setEditValue] = useState('')
  const [isSaving, setIsSaving] = useState(false)

  const [confirmModal, setConfirmModal] = useState<{
    open: boolean;
    title: string;
    description: string;
    onConfirm: () => void | Promise<void>;
    variant?: 'primary' | 'warning' | 'danger';
    confirmText?: string;
  }>({
    open: false,
    title: '',
    description: '',
    onConfirm: () => {},
  })

  const handleEdit = (session: Session) => {
    setEditingSession(session)
    setEditValue(session.journal || '')
  }

  const saveEdit = async () => {
    if (!editingSession) return
    setIsSaving(true)
    try {
      await putJSON(`/v1/sessions/${editingSession.id}/journal`, { journal: editValue })
      await refetch()
      setEditingSession(null)
    } catch (err) {
      console.error('Failed to update journal:', err)
    } finally {
      setIsSaving(false)
    }
  }

  const handleRegenerate = (sessionId: string) => {
    setConfirmModal({
      open: true,
      title: 'Regenerate Journal',
      description: 'This will trigger the Keeper to summarize the session history again. Existing manual edits will be overwritten.',
      variant: 'primary',
      confirmText: 'Regenerate',
      onConfirm: async () => {
        try {
          await postJSON(`/v1/sessions/${sessionId}/journal/regenerate`, {})
          await refetch()
        } catch (err) {
          console.error('Failed to regenerate journal:', err)
        }
      }
    })
  }

  const handleClear = (sessionId: string) => {
    setConfirmModal({
      open: true,
      title: 'Clear Journal',
      description: 'Are you sure you want to clear this journal? This will remove the episodic summary for this session.',
      variant: 'danger',
      confirmText: 'Clear Journal',
      onConfirm: async () => {
        try {
          await deleteJSON(`/v1/sessions/${sessionId}/journal`)
          await refetch()
        } catch (err) {
          console.error('Failed to clear journal:', err)
        }
      }
    })
  }

  if (!agent) return null

  return (
    <div className="flex-1 flex flex-col bg-bg-base h-full w-full min-h-0 font-mono">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-border-dim bg-bg-surface shrink-0">
        <div className="flex items-center gap-4">
          <Link to={`/agents/${id}`}>
            <button className="text-text-secondary hover:text-text-primary transition-colors flex items-center gap-2 text-xs tracking-widest">
              <ChevronLeft className="w-3.5 h-3.5" />
              BACK
            </button>
          </Link>
          <div className="h-4 w-px bg-border-dim" />
          <div className="flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-accent-cyan" />
            <h1 className="text-sm font-bold tracking-[0.2em] text-text-primary uppercase">
              JOURNAL_MANAGEMENT // {agent.name.toUpperCase()}
            </h1>
          </div>
        </div>
        <div className="flex items-center gap-3">
           <Badge variant={agent.status === 'online' ? 'success' : 'default'} className="uppercase tracking-widest text-[9px]">
             {agent.status}
           </Badge>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-8 custom-scrollbar">
        <div className="max-w-5xl mx-auto space-y-6">
          <div className="bg-accent-cyan/5 border border-accent-cyan/20 p-4 flex gap-4">
            <AlertCircle className="w-5 h-5 text-accent-cyan shrink-0" />
            <div className="space-y-1">
              <p className="text-xs font-bold text-accent-cyan uppercase tracking-widest">Operator Guidance</p>
              <p className="text-[11px] text-text-secondary leading-relaxed uppercase">
                Journals represent the compressed episodic memory of an agent for a specific session. 
                Manual overrides will persist until the next automated regeneration or manual clear.
              </p>
            </div>
          </div>

          {isLoading ? (
            <div className="flex items-center justify-center py-20">
              <div className="w-8 h-8 border-2 border-accent-cyan/20 border-t-accent-cyan animate-spin" />
            </div>
          ) : sessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-text-muted space-y-4 opacity-50 border border-dashed border-border-dim">
              <MessageSquare className="w-12 h-12" />
              <p className="text-xs uppercase tracking-widest">No active or historical sessions found</p>
            </div>
          ) : (
            <div className="space-y-4">
              {sessions.map((session) => (
                <div key={session.id} className="bg-bg-surface border border-border-bright overflow-hidden">
                  <div className="px-4 py-3 bg-bg-elevated/50 border-b border-border-dim flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="flex flex-col">
                        <span className="text-[10px] text-text-muted font-bold tracking-widest uppercase">Session ID</span>
                        <span className="text-xs text-text-primary font-mono tabular-nums">{session.id}</span>
                      </div>
                      <div className="h-6 w-px bg-border-dim" />
                      <div className="flex flex-col">
                        <span className="text-[10px] text-text-muted font-bold tracking-widest uppercase">Channel</span>
                        <Badge variant="default" className="text-[9px] h-4">{session.channel?.toUpperCase() || 'UNKNOWN'}</Badge>
                      </div>
                      <div className="h-6 w-px bg-border-dim" />
                      <div className="flex flex-col">
                        <span className="text-[10px] text-text-muted font-bold tracking-widest uppercase">Status</span>
                        <span className={cn(
                          "text-[10px] font-bold uppercase tracking-tight",
                          session.status === 'ready' ? "text-accent-green" : "text-text-muted"
                        )}>{session.status}</span>
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-2">
                       <Button 
                         variant="ghost" 
                         size="sm" 
                         onClick={() => handleEdit(session)}
                         className="h-8 gap-2 text-[10px] tracking-widest text-text-muted hover:text-accent-cyan"
                       >
                         <Edit3 className="w-3.5 h-3.5" />
                         EDIT
                       </Button>
                       <Button 
                         variant="ghost" 
                         size="sm" 
                         onClick={() => handleRegenerate(session.id)}
                         className="h-8 gap-2 text-[10px] tracking-widest text-text-muted hover:text-accent-cyan"
                       >
                         <RefreshCw className="w-3.5 h-3.5" />
                         REGEN
                       </Button>
                       <Button 
                         variant="ghost" 
                         size="sm" 
                         onClick={() => handleClear(session.id)}
                         className="h-8 gap-2 text-[10px] tracking-widest text-text-muted hover:text-accent-red"
                       >
                         <Trash2 className="w-3.5 h-3.5" />
                         CLEAR
                       </Button>
                    </div>
                  </div>

                  <div className="p-4 grid grid-cols-1 md:grid-cols-4 gap-6">
                    <div className="md:col-span-3 space-y-2">
                       <span className="text-[9px] text-text-muted font-bold tracking-widest uppercase flex items-center gap-2">
                         <BookOpen className="w-3 h-3" />
                         Structured Journal Content
                       </span>
                       <div className="bg-black/20 p-4 min-h-[100px] border border-border-dim/50">
                          {session.journal ? (
                            <p className="text-xs text-text-secondary leading-relaxed whitespace-pre-wrap italic font-serif">
                              "{session.journal}"
                            </p>
                          ) : (
                            <p className="text-[10px] text-text-muted uppercase tracking-widest italic py-8 text-center">
                              No journal data available for this session
                            </p>
                          )}
                       </div>
                    </div>
                    
                    <div className="space-y-6">
                       <div className="space-y-1">
                         <span className="text-[9px] text-text-muted font-bold tracking-widest uppercase block">Last Activity</span>
                         <div className="flex items-center gap-2 text-text-secondary">
                           <Calendar className="w-3.5 h-3.5 opacity-50" />
                           <span className="text-[10px] tabular-nums">{session.last_activity_at ? new Date(session.last_activity_at).toLocaleString() : 'NEVER'}</span>
                         </div>
                       </div>
                       
                       <div className="space-y-1">
                         <span className="text-[9px] text-text-muted font-bold tracking-widest uppercase block">Updated At</span>
                         <div className="flex items-center gap-2 text-text-secondary">
                           <RefreshCw className="w-3.5 h-3.5 opacity-50" />
                           <span className="text-[10px] tabular-nums">{session.journal_updated_at ? new Date(session.journal_updated_at).toLocaleString() : 'N/A'}</span>
                         </div>
                       </div>

                       <div className="pt-4 border-t border-border-dim">
                          <div className="flex items-center justify-between">
                             <span className="text-[9px] text-text-muted font-bold tracking-widest uppercase">Tokens</span>
                             <span className="text-[10px] font-mono tabular-nums text-text-primary">{session.token_count}</span>
                          </div>
                       </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <Modal
        open={!!editingSession}
        onClose={() => setEditingSession(null)}
        title={`Edit Journal: ${editingSession?.id.slice(0, 8)}...`}
      >
        <div className="p-6 space-y-4">
          <p className="text-[10px] text-text-muted uppercase tracking-widest leading-relaxed">
            Enter the updated summary for this session. This text will be used as episodic context for future turns.
          </p>
          <Textarea
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            rows={12}
            className="bg-bg-elevated border-border-bright focus:border-accent-cyan text-text-primary font-serif p-4 leading-relaxed"
            placeholder="No journal content..."
          />
          <div className="flex justify-end gap-3 pt-4">
            <Button variant="ghost" onClick={() => setEditingSession(null)}>CANCEL</Button>
            <Button 
              onClick={saveEdit} 
              disabled={isSaving}
              className="bg-accent-cyan text-black font-bold"
            >
              {isSaving ? 'SAVING...' : 'COMMIT_JOURNAL'}
            </Button>
          </div>
        </div>
      </Modal>

      <ConfirmationModal
        open={confirmModal.open}
        title={confirmModal.title}
        description={confirmModal.description}
        variant={confirmModal.variant}
        confirmText={confirmModal.confirmText}
        onConfirm={confirmModal.onConfirm}
        onClose={() => setConfirmModal(prev => ({ ...prev, open: false }))}
      />
    </div>
  )
}
