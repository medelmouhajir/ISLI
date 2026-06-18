import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  useArchivedSessions,
  useRestoreSession,
  useDeleteSession,
  useArchivedSessionHistory,
} from '@/hooks/useSessions'
import { useAgents } from '@/hooks/useAgents'
import { cn } from '@/lib/utils'
import {
  Archive,
  RotateCcw,
  Trash2,
  Eye,
  Bot,
  Loader2,
  MessageSquare,
  Clock,
  User,
  ChevronLeft,
  Users,
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { Modal } from '@/components/ui/Modal'
import { ConfirmationModal } from '@/components/ui/ConfirmationModal'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import { Badge } from '@/components/ui/Badge'
import type { Message } from '@/types'

export function ArchivedSessionsPage() {
  const navigate = useNavigate()
  const { data: archived = [], isLoading } = useArchivedSessions()
  const { data: agents = [] } = useAgents()
  const restore = useRestoreSession()
  const deleteSession = useDeleteSession()

  const [agentFilter, setAgentFilter] = useState<string>('all')
  const [showCouncilSessions, setShowCouncilSessions] = useState(false)
  const [viewSessionId, setViewSessionId] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<{
    open: boolean
    sessionId: string | null
    title: string
    description: string
    variant: 'danger' | 'warning'
    action: 'delete' | 'restore'
  }>({
    open: false,
    sessionId: null,
    title: '',
    description: '',
    variant: 'danger',
    action: 'delete',
  })

  const filteredSessions = useMemo(() => {
    let list = archived || []
    if (!showCouncilSessions) {
      list = list.filter((s) => !s.room_id)
    }
    if (agentFilter !== 'all') {
      list = list.filter((s) => s.agent_id === agentFilter)
    }
    return list
  }, [archived, agentFilter, showCouncilSessions])

  const handleRestore = (sessionId: string) => {
    setConfirm({
      open: true,
      sessionId,
      title: 'Restore Session',
      description: 'Re-open this archived session? It will become active again with status READY.',
      variant: 'warning',
      action: 'restore',
    })
  }

  const handleDelete = (sessionId: string) => {
    setConfirm({
      open: true,
      sessionId,
      title: 'Permanently Delete Session',
      description: 'This will permanently erase the session and all its messages. This action cannot be undone.',
      variant: 'danger',
      action: 'delete',
    })
  }

  const onConfirm = async () => {
    if (!confirm.sessionId) return
    if (confirm.action === 'restore') {
      await restore.mutateAsync(confirm.sessionId)
    } else {
      await deleteSession.mutateAsync(confirm.sessionId)
    }
    setConfirm((prev) => ({ ...prev, open: false, sessionId: null }))
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-bg-base h-full w-full min-h-0">
      {/* Header */}
      <div className="h-16 border-b border-border-dim flex items-center px-4 md:px-6 gap-4 bg-bg-surface shrink-0">
        <button
          onClick={() => navigate('/sessions')}
          className="p-1.5 -ml-1 rounded-none text-text-muted hover:text-text-primary border border-transparent hover:border-border-dim transition-colors"
          title="Back to sessions"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
        <Archive className="w-5 h-5 text-accent-amber" />
        <div>
          <h1 className="text-sm font-mono font-bold text-text-primary uppercase tracking-widest">
            Archive_LOG
          </h1>
          <p className="text-[10px] font-mono text-text-muted uppercase tracking-tighter">
            Closed & Deleted Sessions
          </p>
        </div>
        <div className="ml-auto flex items-center gap-3">
          <button
            onClick={() => setShowCouncilSessions(!showCouncilSessions)}
            className={cn(
              "p-2 rounded-none border transition-all",
              showCouncilSessions
                ? "bg-accent-cyan/10 border-accent-cyan text-accent-cyan shadow-glow-cyan"
                : "bg-bg-elevated border-border-dim text-text-muted hover:text-text-primary hover:border-border-bright"
            )}
            title={showCouncilSessions ? "Hide Council Sessions" : "Show Council Sessions"}
          >
            <Users className="w-4 h-4" />
          </button>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono text-text-muted uppercase">AGENT_FILTER</span>
            <Select
              value={agentFilter}
              onChange={(e) => setAgentFilter(e.target.value)}
              className="w-40 md:w-56"
            >
              <option value="all">ALL_AGENTS</option>
              {agents.map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.name}
                </option>
              ))}
            </Select>
          </div>
          <Badge variant="warning" className="tabular-nums">
            {filteredSessions.length} ARCHIVED
          </Badge>
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6">
        {isLoading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-8 h-8 text-accent-cyan animate-spin" />
          </div>
        ) : filteredSessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center border border-dashed border-border-dim bg-bg-surface/30 p-12">
            <Archive className="w-12 h-12 text-text-muted opacity-20 mb-4" />
            <h3 className="text-sm font-mono font-bold text-text-primary uppercase tracking-widest mb-2">
              NO_ARCHIVED_SESSIONS_FOUND
            </h3>
            <p className="text-[10px] font-mono text-text-muted max-w-xs uppercase tracking-tight opacity-70">
              Archived sessions appear here after being closed or soft-deleted by lifecycle policies.
            </p>
          </div>
        ) : (
          <div className="grid gap-3">
            {filteredSessions.map((session) => {
              const agent = agents.find((a) => a.id === session.agent_id)
              const isDeleted = !!session.deleted_at
              const messageCount = session.messages?.length || 0
              const timestamp = isDeleted ? session.deleted_at : undefined

              return (
                <div
                  key={session.id}
                  className="group flex flex-col md:flex-row md:items-center gap-3 md:gap-4 p-4 bg-bg-surface border border-border-dim hover:border-border-bright transition-colors"
                >
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <div className="w-10 h-10 rounded-none bg-accent-cyan/5 border border-accent-cyan/20 flex items-center justify-center text-accent-cyan overflow-hidden shrink-0">
                      {agent?.picture ? (
                        <img
                          src={`/api/v1/blobs/${agent.picture}`}
                          alt={agent.name}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <Bot className="w-5 h-5" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-mono font-bold text-text-primary truncate">
                          {agent?.name || 'UNKNOWN_AGENT'}
                        </span>
                        <Badge variant={isDeleted ? 'danger' : 'warning'}>
                          {isDeleted ? 'DELETED' : 'CLOSED'}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-[10px] font-mono text-text-muted uppercase tracking-tighter">
                        <span>ID::{session.id.slice(0, 8)}</span>
                        {session.user_id && <span>USER::{session.user_id}</span>}
                        {session.channel && <span>CHAN::{session.channel}</span>}
                        <span className="flex items-center gap-1">
                          <MessageSquare className="w-3 h-3" />
                          {messageCount} MSG
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between md:justify-end gap-4">
                    <div className="flex items-center gap-1.5 text-[10px] font-mono text-text-muted uppercase">
                      <Clock className="w-3 h-3" />
                      {timestamp ? formatDistanceToNow(new Date(timestamp), { addSuffix: true }) : '—'}
                    </div>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setViewSessionId(session.id)}
                        title="View history"
                      >
                        <Eye className="w-4 h-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRestore(session.id)}
                        disabled={restore.isPending}
                        title="Restore session"
                      >
                        <RotateCcw className="w-4 h-4 text-accent-green" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(session.id)}
                        disabled={deleteSession.isPending}
                        title="Permanently delete"
                      >
                        <Trash2 className="w-4 h-4 text-accent-red" />
                      </Button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* View history modal */}
      <SessionHistoryModal
        sessionId={viewSessionId}
        onClose={() => setViewSessionId(null)}
        agents={agents}
      />

      <ConfirmationModal
        open={confirm.open}
        title={confirm.title}
        description={confirm.description}
        variant={confirm.variant}
        confirmText={confirm.action === 'restore' ? 'Restore' : 'Permanently Delete'}
        onConfirm={onConfirm}
        onClose={() => setConfirm((prev) => ({ ...prev, open: false, sessionId: null }))}
        isLoading={confirm.action === 'restore' ? restore.isPending : deleteSession.isPending}
      />
    </div>
  )
}

interface SessionHistoryModalProps {
  sessionId: string | null
  onClose: () => void
  agents: { id: string; name: string; picture?: string | null }[]
}

function SessionHistoryModal({ sessionId, onClose, agents }: SessionHistoryModalProps) {
  const { data: history, isLoading } = useArchivedSessionHistory(sessionId)
  const activeAgent = history ? agents.find((a) => a.id === history.agent_id) : undefined

  return (
    <Modal
      open={!!sessionId}
      onClose={onClose}
      title="Archived Session History"
      className="sm:max-w-3xl"
      scrollable
    >
      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 text-accent-cyan animate-spin" />
        </div>
      ) : !history ? (
        <div className="text-center py-8 text-text-muted font-mono text-xs uppercase">
          SESSION_NOT_FOUND
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center gap-3 pb-3 border-b border-border-dim">
            <div className="w-9 h-9 rounded-none bg-accent-cyan/5 border border-accent-cyan/20 flex items-center justify-center text-accent-cyan overflow-hidden">
              {activeAgent?.picture ? (
                <img
                  src={`/api/v1/blobs/${activeAgent.picture}`}
                  alt={activeAgent.name}
                  className="w-full h-full object-cover"
                />
              ) : (
                <Bot className="w-5 h-5" />
              )}
            </div>
            <div>
              <p className="text-sm font-mono font-bold text-text-primary">
                {activeAgent?.name || history.agent_id}
              </p>
              <p className="text-[10px] font-mono text-text-muted uppercase">
                {history.user_id ? `USER::${history.user_id}` : 'NO_USER'} ·{' '}
                {history.channel ? `CHAN::${history.channel}` : 'NO_CHANNEL'}
              </p>
            </div>
          </div>

          <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-2">
            {history.all_messages.length === 0 ? (
              <p className="text-center text-[10px] font-mono text-text-muted uppercase py-8">
                NO_MESSAGES_IN_HISTORY
              </p>
            ) : (
              history.all_messages.map((msg: Message, i: number) => (
                <MessageRow key={i} msg={msg} agent={activeAgent} />
              ))
            )}
          </div>
        </div>
      )}
    </Modal>
  )
}

function MessageRow({
  msg,
  agent,
}: {
  msg: Message
  agent?: { id: string; name: string; picture?: string | null }
}) {
  const isUser = msg.role === 'user'
  const isAction = msg.role === 'action'

  return (
    <div
      className={cn(
        'flex gap-3 max-w-[90%]',
        isUser || isAction ? 'ml-auto flex-row-reverse' : ''
      )}
    >
      <div
        className={cn(
          'w-8 h-8 rounded-none shrink-0 flex items-center justify-center border overflow-hidden',
          isUser
            ? 'bg-accent-purple/5 border-accent-purple/20 text-accent-purple'
            : isAction
              ? 'bg-accent-amber/5 border-accent-amber/20 text-accent-amber'
              : 'bg-accent-cyan/5 border-accent-cyan/20 text-accent-cyan'
        )}
      >
        {isUser ? (
          <User className="w-4 h-4" />
        ) : isAction ? (
          <Clock className="w-4 h-4" />
        ) : agent?.picture ? (
          <img
            src={`/api/v1/blobs/${agent.picture}`}
            alt={agent.name}
            className="w-full h-full object-cover"
          />
        ) : (
          <Bot className="w-4 h-4" />
        )}
      </div>
      <div className={cn('space-y-1', isUser || isAction ? 'text-right' : '')}>
        <div
          className={cn(
            'p-3 rounded-none text-sm leading-relaxed border font-mono',
            isUser
              ? 'bg-accent-purple/5 border-accent-purple/20 text-text-primary'
              : isAction
                ? 'bg-accent-amber/5 border-accent-amber/20 text-text-muted'
                : 'bg-bg-elevated border-border-dim text-text-primary'
          )}
        >
          {msg.content}
        </div>
        {isAction && msg.action_type && (
          <div className="text-[10px] font-mono text-text-muted italic px-2">
            ↳ {msg.action_type.replace(/_/g, ' ')} on {msg.action_id}
          </div>
        )}
        <div
          className={cn(
            'flex items-center gap-2 text-[9px] text-text-muted px-1 font-mono uppercase',
            isUser || isAction ? 'justify-end' : ''
          )}
        >
          <Clock className="w-3 h-3" />
          {msg.timestamp ? new Date(msg.timestamp).toLocaleString([], { hour12: false }) : '—'}
        </div>
      </div>
    </div>
  )
}
