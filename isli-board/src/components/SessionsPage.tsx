import { useState, useMemo } from 'react'
import { useSessions, useSession, useSendMessage, useCreateSession, useCloseSession, useDeleteSession } from '@/hooks/useSessions'
import { useAgents } from '@/hooks/useAgents'
import { cn } from '@/lib/utils'
import { MessageSquare, Send, Plus, Bot, User, Clock, Loader2, Archive, Trash2, ChevronLeft } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { Modal } from '@/components/ui/Modal'

export function SessionsPage() {
  const { data: sessions = [], isLoading: loadingSessions } = useSessions()
  const { data: agents = [] } = useAgents()
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  
  const sortedSessions = useMemo(() => {
    return [...sessions].sort((a, b) => {
      const aLastMsg = a.messages && a.messages.length > 0 ? a.messages[a.messages.length - 1] : null
      const bLastMsg = b.messages && b.messages.length > 0 ? b.messages[b.messages.length - 1] : null
      
      const aTime = aLastMsg?.timestamp ? new Date(aLastMsg.timestamp).getTime() : new Date(a.last_activity_at || 0).getTime()
      const bTime = bLastMsg?.timestamp ? new Date(bLastMsg.timestamp).getTime() : new Date(b.last_activity_at || 0).getTime()
      
      return bTime - aTime
    })
  }, [sessions])

  const { data: selectedSession } = useSession(selectedSessionId)
  const [messageText, setMessageText] = useState('')
  const sendMessage = useSendMessage()
  const createSession = useCreateSession()
  const closeSession = useCloseSession()
  const deleteSession = useDeleteSession()

  const handleCloseSession = async (sessionId: string) => {
    await closeSession.mutateAsync(sessionId)
    if (selectedSessionId === sessionId) setSelectedSessionId(null)
  }

  const handleDeleteSession = async (sessionId: string) => {
    if (!confirm('Permanently delete this conversation?')) return
    await deleteSession.mutateAsync(sessionId)
    if (selectedSessionId === sessionId) setSelectedSessionId(null)
  }

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!messageText.trim() || !selectedSessionId) return
    const text = messageText
    setMessageText('')
    await sendMessage.mutateAsync({ sessionId: selectedSessionId, text })
  }

  const handleCreateSession = async (agentId: string) => {
    const session = await createSession.mutateAsync({ agent_id: agentId })
    setSelectedSessionId(session.id)
    setIsModalOpen(false)
  }

  return (
    <div className="flex-1 flex overflow-hidden bg-bg-base h-full w-full min-h-0">
      {/* Sessions List */}
      <div className={cn(
        "w-full md:w-80 border-r border-border-dim flex flex-col bg-bg-surface h-full min-h-0 transition-all",
        selectedSessionId ? "hidden md:flex" : "flex"
      )}>
        <div className="p-4 border-b border-border-dim flex items-center justify-between bg-bg-surface">
          <h2 className="text-xs font-mono font-bold text-text-primary uppercase tracking-widest">
            Sessions_LOG
          </h2>
          <button
            onClick={() => setIsModalOpen(true)}
            className="p-1.5 rounded-none bg-bg-elevated border border-border-dim text-accent-cyan hover:border-accent-cyan transition-all"
            title="New Chat"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>

        <Modal open={isModalOpen} onClose={() => setIsModalOpen(false)} title="Initialize Agent" className="sm:max-w-xl rounded-none font-mono">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {agents.map(agent => (
              <button
                key={agent.id}
                onClick={() => handleCreateSession(agent.id)}
                className="flex flex-col gap-2 p-4 rounded-none bg-bg-elevated border border-border-dim hover:border-accent-cyan transition-all text-left group"
              >
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-none bg-accent-cyan/10 flex items-center justify-center text-accent-cyan border border-accent-cyan/20">
                    <Bot className="w-4 h-4" />
                  </div>
                  <span className="text-sm font-mono font-bold text-text-primary group-hover:text-accent-cyan transition-colors">{agent.name}</span>
                </div>
                <p className="text-xs text-text-secondary line-clamp-2 font-mono opacity-70">{agent.description}</p>
              </button>
            ))}
          </div>
        </Modal>

        <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
          {loadingSessions ? (
            <div className="flex justify-center py-8">
              <Loader2 className="w-6 h-6 text-accent-cyan animate-spin" />
            </div>
          ) : !sessions || sessions.length === 0 ? (
            <div className="text-center py-12 px-4 border border-dashed border-border-dim m-2">
              <MessageSquare className="w-8 h-8 text-text-muted mx-auto mb-3 opacity-20" />
              <p className="text-[10px] font-mono text-text-muted uppercase tracking-widest">No active sessions</p>
            </div>
          ) : (
            sortedSessions.map((s) => {
              const agent = agents?.find(a => a.id === s.agent_id)
              const lastMsg = s.messages && s.messages.length > 0 ? s.messages[s.messages.length - 1] : null
              return (
                <div
                  key={s.id}
                  onClick={() => setSelectedSessionId(s.id)}
                  className={cn(
                    'w-full text-left p-3 rounded-none border transition-all duration-100 group cursor-pointer',
                    selectedSessionId === s.id
                      ? 'bg-accent-cyan/5 border-accent-cyan'
                      : 'bg-transparent border-transparent hover:bg-bg-elevated hover:border-border-dim'
                  )}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className={cn(
                      'text-xs font-mono font-bold truncate tracking-tight',
                      selectedSessionId === s.id ? 'text-accent-cyan' : 'text-text-primary'
                    )}>
                      {agent?.name || 'UNKNOWN_AGENT'}
                    </span>
                    <div className="flex items-center gap-1">
                      {(lastMsg?.timestamp || s.last_activity_at) && (
                        <span className="text-[9px] font-mono text-text-muted whitespace-nowrap tabular-nums">
                          {formatDistanceToNow(new Date(lastMsg?.timestamp || s.last_activity_at!), { addSuffix: true })}
                        </span>
                      )}
                      <button
                        onClick={(e) => { e.stopPropagation(); handleCloseSession(s.id) }}
                        className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded-none text-text-muted hover:text-accent-amber hover:bg-accent-amber/10 border border-transparent hover:border-accent-amber/20"
                        title="Close conversation"
                      >
                        <Archive className="w-3 h-3" />
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDeleteSession(s.id) }}
                        className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded-none text-text-muted hover:text-accent-red hover:bg-accent-red/10 border border-transparent hover:border-accent-red/20"
                        title="Delete conversation"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  </div>
                  <p className="text-[11px] font-mono text-text-secondary truncate line-clamp-1 opacity-60">
                    {lastMsg ? lastMsg.content : '--- INITIALIZED ---'}
                  </p>
                  <div className="mt-2 flex items-center gap-2">
                    <span className={cn(
                      'w-1.5 h-1.5 rounded-none',
                      s.status === 'ready' ? 'bg-accent-green' : 'bg-accent-amber animate-pulse'
                    )} />
                    <span className="text-[9px] uppercase tracking-tighter text-text-muted font-mono font-bold">
                      STATUS::{s.status}
                    </span>
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* Chat Area */}
      <div className={cn(
        "flex-1 flex flex-col bg-bg-base relative min-h-0",
        !selectedSessionId ? "hidden md:flex" : "flex"
      )}>
        {selectedSessionId ? (
          selectedSession ? (
            <>
              {/* Chat Header */}
              <div className="h-14 border-b border-border-dim flex items-center px-4 md:px-6 gap-3 md:gap-4 bg-bg-surface shrink-0">
                <button
                  onClick={() => setSelectedSessionId(null)}
                  className="p-1.5 -ml-1 rounded-none text-text-muted hover:text-text-primary border border-transparent hover:border-border-dim md:hidden"
                >
                  <ChevronLeft className="w-5 h-5" />
                </button>
                <div className="w-8 h-8 md:w-9 md:h-9 rounded-none bg-accent-cyan/5 border border-accent-cyan/20 flex items-center justify-center text-accent-cyan">
                  <Bot className="w-5 h-5 md:w-6 md:h-6" />
                </div>
                <div>
                  <h3 className="text-xs md:text-sm font-mono font-bold text-text-primary uppercase tracking-tight">
                    {agents?.find(a => a.id === selectedSession.agent_id)?.name || 'SESSION_ID'}
                  </h3>
                  <div className="flex items-center gap-2">
                    <span className={cn(
                      'w-1.5 h-1.5 rounded-none',
                      selectedSession.status === 'ready' ? 'bg-accent-green' : 'bg-accent-amber animate-pulse'
                    )} />
                    <span className="text-[9px] text-text-muted uppercase tracking-widest font-mono font-bold">
                      {selectedSession.status}
                    </span>
                  </div>
                </div>
                <div className="ml-auto flex items-center gap-1">
                  <button
                    onClick={() => handleCloseSession(selectedSession.id)}
                    className="p-2 rounded-none text-text-muted hover:text-accent-amber hover:bg-accent-amber/5 border border-transparent hover:border-accent-amber/20 transition-colors"
                    title="Close conversation"
                  >
                    <Archive className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleDeleteSession(selectedSession.id)}
                    className="p-2 rounded-none text-text-muted hover:text-accent-red hover:bg-accent-red/5 border border-transparent hover:border-accent-red/20 transition-colors"
                    title="Delete conversation"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6 min-h-0 scrollbar-thin">
                {selectedSession.messages?.map((msg, i) => (
                  <div
                    key={i}
                    className={cn(
                      'flex gap-3 md:gap-4 max-w-[90%] md:max-w-[80%]',
                      msg.role === 'user' ? 'ml-auto flex-row-reverse' : ''
                    )}
                  >
                    <div className={cn(
                      'w-8 h-8 rounded-none shrink-0 flex items-center justify-center border',
                      msg.role === 'user' 
                        ? 'bg-accent-purple/5 border-accent-purple/20 text-accent-purple'
                        : 'bg-accent-cyan/5 border-accent-cyan/20 text-accent-cyan'
                    )}>
                      {msg.role === 'user' ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                    </div>
                    <div className={cn(
                      'space-y-1',
                      msg.role === 'user' ? 'text-right' : ''
                    )}>
                      <div className={cn(
                        'p-3 md:p-4 rounded-none text-sm leading-relaxed border font-mono',
                        msg.role === 'user'
                          ? 'bg-accent-purple/5 border-accent-purple/20 text-text-primary'
                          : 'bg-bg-elevated border-border-dim text-text-primary'
                      )}>
                        {msg.content}
                      </div>
                      <div className={cn(
                        "flex items-center gap-2 text-[9px] text-text-muted px-1 font-mono uppercase",
                        msg.role === 'user' ? "justify-end" : ""
                      )}>
                        <Clock className="w-3 h-3" />
                        {msg.timestamp && new Date(msg.timestamp).toLocaleTimeString([], { hour12: false })}
                      </div>
                    </div>
                  </div>
                ))}
                {selectedSession.status !== 'ready' && (
                  <div className="flex gap-4 max-w-[80%]">
                    <div className="w-8 h-8 rounded-none shrink-0 flex items-center justify-center border bg-accent-cyan/5 border-accent-cyan/20 text-accent-cyan">
                      <Bot className="w-4 h-4" />
                    </div>
                    <div className="bg-bg-elevated border border-border-dim p-4 rounded-none flex items-center gap-3">
                      <div className="flex gap-1">
                        <span className="w-1.5 h-1.5 rounded-none bg-accent-cyan animate-pulse" />
                        <span className="w-1.5 h-1.5 rounded-none bg-accent-cyan animate-pulse [animation-delay:0.2s]" />
                        <span className="w-1.5 h-1.5 rounded-none bg-accent-cyan animate-pulse [animation-delay:0.4s]" />
                      </div>
                      <span className="text-[9px] font-mono font-bold text-text-muted uppercase tracking-widest">
                        {selectedSession.status === 'pending_context' ? 'INJECTING_CONTEXT...' : 'THINKING...'}
                      </span>
                    </div>
                  </div>
                )}
              </div>

              {/* Input */}
              <div className="p-4 md:p-6 border-t border-border-dim bg-bg-surface shrink-0">
                <form onSubmit={handleSendMessage} className="relative flex gap-2">
                  <input
                    type="text"
                    value={messageText}
                    onChange={(e) => setMessageText(e.target.value)}
                    placeholder="ENTER COMMAND OR MESSAGE..."
                    className="flex-1 bg-bg-elevated border border-border-dim rounded-none px-4 py-3 text-sm font-mono focus:outline-none focus:border-accent-cyan transition-all placeholder:opacity-30"
                  />
                  <button
                    type="submit"
                    disabled={!messageText.trim() || sendMessage.isPending}
                    className="px-4 rounded-none bg-accent-cyan text-bg-base font-mono font-bold hover:bg-accent-cyan/90 transition-all disabled:opacity-30 flex items-center justify-center min-w-[60px]"
                  >
                    {sendMessage.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                  </button>
                </form>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center bg-bg-base">
              <div className="flex flex-col items-center gap-2">
                <Loader2 className="w-8 h-8 text-accent-cyan animate-spin" />
                <span className="text-[10px] font-mono text-text-muted uppercase tracking-tighter">loading_session_stream...</span>
              </div>
            </div>
          )
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center p-12 text-center bg-bg-base">
            <div className="w-20 h-20 rounded-none bg-bg-elevated border border-border-dim flex items-center justify-center text-text-muted mb-6">
              <MessageSquare className="w-10 h-10 opacity-10" />
            </div>
            <h3 className="text-sm font-mono font-bold text-text-primary mb-2 uppercase tracking-widest">
              SYSTEM_AWAITING_INPUT
            </h3>
            <p className="text-[10px] font-mono text-text-muted max-w-xs uppercase tracking-tight opacity-70">
              Select an active session from the sidebar or initialize a new agent interaction.
            </p>
          </div>
        )
        }
      </div>
    </div>
  )
}
