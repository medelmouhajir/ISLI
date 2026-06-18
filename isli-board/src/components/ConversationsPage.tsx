import { useState, useMemo, useCallback, useEffect, useRef } from 'react'
import { useChatSessions, useSessionHistory, useSendChatMessage } from '@/hooks/useChats'
import { useAgents } from '@/hooks/useAgents'
import { useSessionAction } from '@/hooks/useSessionAction'
import { useSessionStream } from '@/hooks/useSessionStream'
import { cn } from '@/lib/utils'
import { Select } from '@/components/ui/Select'
import {
  MessageSquare,
  Bot,
  User,
  Clock,
  Loader2,
  ChevronLeft,
  MessageCircle,
  Hash,
  ArrowDown,
} from 'lucide-react'
import { ChatInput } from '@/components/ChatInput'
import { formatDistanceToNow } from 'date-fns'
import { UiComponentRenderer } from '@/components/ui/registry/UiComponentRegistry'
import { StreamingMessageBubble } from '@/components/StreamingMessageBubble'
import { ToolCallBar } from '@/components/ToolCallCard'
import { ProcessTracePane } from '@/components/ProcessTracePane'
import { AttachmentList } from '@/components/AttachmentList'
import type { ComponentPayload, ToolCallEvent, ProcessTraceEvent } from '@/types'

export function ConversationsPage() {
  const { data: agents = [] } = useAgents()
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null)
  const [selectedChannel, setSelectedChannel] = useState<string | null>(null)
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null)

  const selectedAgent = agents.find((a) => a.id === selectedAgentId)
  const availableChannels = selectedAgent?.channels || []

  const { data: sessions = [], isLoading: loadingSessions } = useChatSessions(
    selectedAgentId || undefined,
    selectedChannel || undefined
  )

  // Group sessions by user_id and pick the latest session per client
  const clients = useMemo(() => {
    const grouped = new Map<string, typeof sessions>()
    for (const s of sessions) {
      const key = s.user_id || 'unknown'
      if (!grouped.has(key)) grouped.set(key, [])
      grouped.get(key)!.push(s)
    }
    return Array.from(grouped.entries())
      .map(([userId, userSessions]) => {
        const sorted = [...userSessions].sort(
          (a, b) =>
            new Date(b.last_activity_at || 0).getTime() -
            new Date(a.last_activity_at || 0).getTime()
        )
        const latest = sorted[0]
        const lastMsg =
          latest.messages && latest.messages.length > 0
            ? latest.messages[latest.messages.length - 1]
            : null
        const anyReady = userSessions.some((s) => s.status === 'ready')
        const anyPending = userSessions.some((s) =>
          ['pending_context', 'processing_context', 'agent_processing'].includes(s.status)
        )
        const allClosed = userSessions.every((s) => s.status === 'closed')
        const statusColor = anyPending
          ? 'bg-accent-amber'
          : anyReady
            ? 'bg-accent-green'
            : allClosed
              ? 'bg-text-muted'
              : 'bg-accent-amber'

        return {
          userId,
          latestSession: latest,
          sessionCount: userSessions.length,
          lastMsg,
          statusColor,
        }
      })
      .sort(
        (a, b) =>
          new Date(b.latestSession.last_activity_at || 0).getTime() -
          new Date(a.latestSession.last_activity_at || 0).getTime()
      )
  }, [sessions])

  const activeClient = clients.find((c) => c.userId === selectedUserId)
  const activeSessionId = activeClient?.latestSession.id || null

  const { data: history, isLoading: loadingHistory } = useSessionHistory(activeSessionId)
  const [messageText, setMessageText] = useState('')
  const [voiceModeEnabled, setVoiceModeEnabled] = useState(false)
  const sendMessage = useSendChatMessage()
  const postSessionAction = useSessionAction()
  const streamEvent = useSessionStream()

  // Streaming state
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [toolCalls, setToolCalls] = useState<Record<string, ToolCallEvent[]>>({})
  const [processTraces, setProcessTraces] = useState<Record<string, ProcessTraceEvent[]>>({})
  const [lastStatusText, setLastStatusText] = useState<Record<string, string>>({})

  // Scroll management
  const containerRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const isAtBottomRef = useRef(true)
  const prevSessionIdRef = useRef<string | null>(null)
  const [showScrollIndicator, setShowScrollIndicator] = useState(false)
  const [unreadCount, setUnreadCount] = useState(0)

  const handleScroll = useCallback(() => {
    const el = containerRef.current
    if (!el) return
    // Using a 100px threshold for "at bottom" to be safer
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100
    isAtBottomRef.current = atBottom
    setShowScrollIndicator(!atBottom)
    if (atBottom) {
      setUnreadCount(0)
    }
  }, [])

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    if (!bottomRef.current) return
    bottomRef.current.scrollIntoView({ behavior })
    if (behavior === 'smooth' || isAtBottomRef.current) {
      setUnreadCount(0)
      setShowScrollIndicator(false)
    }
  }, [])

  // Handle scrolling logic
  useEffect(() => {
    if (!activeSessionId) return

    const isNewSession = prevSessionIdRef.current !== activeSessionId
    prevSessionIdRef.current = activeSessionId

    if (isNewSession) {
      // Instant scroll on session switch
      isAtBottomRef.current = true
      setUnreadCount(0)
      setShowScrollIndicator(false)
      // Use requestAnimationFrame to ensure DOM is updated
      requestAnimationFrame(() => {
        scrollToBottom('instant')
      })
      return
    }

    // Auto-scroll on new content if already at bottom
    if (isAtBottomRef.current) {
      scrollToBottom('smooth')
    } else {
      // If not at bottom and history length changed, we have unread messages
      // We also explicitly show the scroll indicator here
      setUnreadCount((prev) => prev + 1)
      setShowScrollIndicator(true)
    }
  }, [
    activeSessionId,
    history?.all_messages.length,
    drafts[activeSessionId || ''],
    toolCalls[activeSessionId || ''],
    scrollToBottom,
  ])

  useEffect(() => {
    if (!streamEvent || streamEvent.session_id !== activeSessionId) return

    const { event_type, data, timestamp } = streamEvent

    if (event_type === 'token_delta' && typeof data.delta === 'string') {
      setDrafts((prev) => ({
        ...prev,
        [streamEvent.session_id]: (prev[streamEvent.session_id] || '') + data.delta,
      }))
    }

    if (event_type === 'draft_complete') {
      // Draft is complete; final message will arrive via session:updated
      // We keep the draft visible until the final message arrives
    }

    if (event_type === 'tool_call') {
      setToolCalls((prev) => {
        const existing = prev[streamEvent.session_id] || []
        const filtered = existing.filter((t) => t.tool !== data.tool)
        const next = [
          ...filtered,
          {
            tool: String(data.tool),
            status: data.status as 'started' | 'done',
            result_summary: data.result_summary as string | undefined,
            duration_ms: data.duration_ms as number | undefined,
          },
        ]
        return { ...prev, [streamEvent.session_id]: next }
      })
      if (data.status === 'started') {
        setLastStatusText((prev) => ({
          ...prev,
          [streamEvent.session_id]: `USING_SKILL: ${data.tool}...`,
        }))
      }
    }

    if (event_type === 'phase_start') {
      const phase = String(data.phase || '')
      setLastStatusText((prev) => ({
        ...prev,
        [streamEvent.session_id]:
          phase === 'context_inject'
            ? 'INJECTING_CONTEXT...'
            : phase === 'checkpoint'
              ? 'SAVING_CHECKPOINT...'
              : 'THINKING...',
      }))
    }

    // Accumulate process trace events
    if (['phase_start', 'phase_end', 'turn_start', 'turn_end', 'cost_report', 'debug_prompt', 'debug_response', 'error'].includes(event_type)) {
      setProcessTraces((prev) => ({
        ...prev,
        [streamEvent.session_id]: [
          ...(prev[streamEvent.session_id] || []),
          { event_type, data, timestamp },
        ],
      }))
    }
  }, [streamEvent, activeSessionId])

  // Clear streaming state when a session becomes ready
  useEffect(() => {
    if (activeClient?.latestSession.status === 'ready') {
      setDrafts((prev) => {
        const { [activeSessionId || '']: _, ...rest } = prev
        return rest
      })
      setToolCalls((prev) => {
        const { [activeSessionId || '']: _, ...rest } = prev
        return rest
      })
      setLastStatusText((prev) => {
        const { [activeSessionId || '']: _, ...rest } = prev
        return rest
      })
    }
  }, [activeClient?.latestSession.status, activeSessionId])

  const handleSendMessage = async (text: string, voiceMode?: boolean) => {
    if (!text.trim() || !activeSessionId) return
    setMessageText('')
    await sendMessage.mutateAsync({ sessionId: activeSessionId, text, voiceMode })
  }

  const handleComponentAction = useCallback(
    (actionId: string, actionType: string, payload: Record<string, unknown>) => {
      if (!activeSessionId || !history || activeClient?.latestSession.status !== 'ready') return
      postSessionAction.mutate({
        sessionId: activeSessionId,
        action: { action_id: actionId, action_type: actionType, payload },
      })
    },
    [activeSessionId, history, activeClient, postSessionAction]
  )

  const handleSelectAgent = (agentId: string) => {
    setSelectedAgentId(agentId || null)
    setSelectedChannel(null)
    setSelectedUserId(null)
  }

  const handleSelectChannel = (channel: string) => {
    setSelectedChannel(channel || null)
    setSelectedUserId(null)
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-bg-base h-full w-full min-h-0">
      {/* Top filter bar */}
      <div className="h-14 border-b border-border-dim flex items-center px-4 gap-3 bg-bg-surface shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-none bg-accent-cyan/10 border border-accent-cyan/20 flex items-center justify-center overflow-hidden shrink-0">
            {selectedAgent?.picture ? (
              <img
                src={`/api/v1/blobs/${selectedAgent.picture}`}
                alt={selectedAgent.name}
                className="w-full h-full object-cover"
              />
            ) : (
              <Bot className="w-3.5 h-3.5 text-text-muted" />
            )}
          </div>
          <Select
            value={selectedAgentId || ''}
            onChange={(e) => handleSelectAgent(e.target.value)}
            className="w-48"
          >
            <option value="">SELECT_AGENT</option>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </Select>
        </div>

        <div className="flex items-center gap-2">
          <Hash className="w-4 h-4 text-text-muted" />
          <Select
            value={selectedChannel || ''}
            onChange={(e) => handleSelectChannel(e.target.value)}
            disabled={!selectedAgentId || availableChannels.length === 0}
            className="w-48"
          >
            <option value="">SELECT_CHANNEL</option>
            {availableChannels.map((c) => (
              <option key={c} value={c}>
                {c.toUpperCase()}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Client list */}
        <div
          className={cn(
            'w-full md:w-80 border-r border-border-dim flex flex-col bg-bg-surface h-full min-h-0 transition-all',
            selectedUserId ? 'hidden md:flex' : 'flex'
          )}
        >
          <div className="p-4 border-b border-border-dim flex items-center justify-between bg-bg-surface">
            <h2 className="text-xs font-mono font-bold text-text-primary uppercase tracking-widest">
              Clients_LOG
            </h2>
            <span className="text-[10px] font-mono-data text-text-muted">
              {clients.length} clients
            </span>
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
            {loadingSessions ? (
              <div className="flex justify-center py-8">
                <Loader2 className="w-6 h-6 text-accent-cyan animate-spin" />
              </div>
            ) : !selectedAgentId || !selectedChannel ? (
              <div className="text-center py-12 px-4 border border-dashed border-border-dim m-2">
                <MessageCircle className="w-8 h-8 text-text-muted mx-auto mb-3 opacity-20" />
                <p className="text-[10px] font-mono text-text-muted uppercase tracking-widest">
                  Select an agent and channel
                </p>
              </div>
            ) : clients.length === 0 ? (
              <div className="text-center py-12 px-4 border border-dashed border-border-dim m-2">
                <MessageSquare className="w-8 h-8 text-text-muted mx-auto mb-3 opacity-20" />
                <p className="text-[10px] font-mono text-text-muted uppercase tracking-widest">
                  No conversations for this agent + channel
                </p>
              </div>
            ) : (
              clients.map((client) => (
                <div
                  key={client.userId}
                  onClick={() => setSelectedUserId(client.userId)}
                  className={cn(
                    'w-full text-left p-3 rounded-none border transition-all duration-100 group cursor-pointer',
                    selectedUserId === client.userId
                      ? 'bg-accent-cyan/5 border-accent-cyan'
                      : 'bg-transparent border-transparent hover:bg-bg-elevated hover:border-border-dim'
                  )}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span
                      className={cn(
                        'text-xs font-mono font-bold truncate tracking-tight',
                        selectedUserId === client.userId
                          ? 'text-accent-cyan'
                          : 'text-text-primary'
                      )}
                    >
                      {client.userId}
                    </span>
                    <div className="flex items-center gap-1.5">
                      {client.sessionCount > 1 && (
                        <span className="text-[9px] font-mono-data bg-bg-elevated border border-border-dim px-1 py-0.5 text-text-muted">
                          {client.sessionCount} sessions
                        </span>
                      )}
                      <span
                        className={cn(
                          'w-1.5 h-1.5 rounded-none',
                          client.statusColor,
                          client.statusColor === 'bg-accent-amber' && 'animate-pulse'
                        )}
                      />
                    </div>
                  </div>
                  <p className="text-[11px] font-mono text-text-secondary truncate line-clamp-1 opacity-60">
                    {client.lastMsg ? client.lastMsg.content : '--- NO MESSAGES ---'}
                  </p>
                  <div className="mt-1.5 flex items-center gap-2">
                    <Clock className="w-3 h-3 text-text-muted" />
                    <span className="text-[9px] font-mono text-text-muted whitespace-nowrap tabular-nums">
                      {client.latestSession.last_activity_at
                        ? formatDistanceToNow(
                            new Date(client.latestSession.last_activity_at),
                            { addSuffix: true }
                          )
                        : '---'}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Chat area */}
        <div
          className={cn(
            'flex-1 flex flex-col bg-bg-base relative min-h-0',
            !selectedUserId ? 'hidden md:flex' : 'flex'
          )}
        >
          {selectedUserId ? (
            activeClient ? (
              <>
                {/* Chat header */}
                <div className="h-14 border-b border-border-dim flex items-center px-4 md:px-6 gap-3 md:gap-4 bg-bg-surface shrink-0">
                  <button
                    onClick={() => setSelectedUserId(null)}
                    className="p-1.5 -ml-1 rounded-none text-text-muted hover:text-text-primary border border-transparent hover:border-border-dim md:hidden"
                  >
                    <ChevronLeft className="w-5 h-5" />
                  </button>
                  <div className="w-8 h-8 md:w-9 md:h-9 rounded-none bg-accent-cyan/5 border border-accent-cyan/20 flex items-center justify-center text-accent-cyan">
                    <User className="w-5 h-5 md:w-6 md:h-6" />
                  </div>
                  <div>
                    <h3 className="text-xs md:text-sm font-mono font-bold text-text-primary uppercase tracking-tight">
                      {activeClient.userId}
                    </h3>
                    <div className="flex items-center gap-2">
                      <span className="text-[9px] text-text-muted uppercase tracking-widest font-mono font-bold">
                        {selectedAgent?.name} / {selectedChannel}
                      </span>
                    </div>
                  </div>
                  <div className="ml-auto flex items-center gap-2">
                    <span
                      className={cn(
                        'text-[9px] font-mono font-bold uppercase tracking-tighter px-2 py-1 border',
                        activeClient.latestSession.status === 'ready'
                          ? 'text-accent-green border-accent-green/20 bg-accent-green/5'
                          : activeClient.latestSession.status === 'closed'
                            ? 'text-text-muted border-border-dim bg-bg-elevated'
                            : 'text-accent-amber border-accent-amber/20 bg-accent-amber/5'
                      )}
                    >
                      {activeClient.latestSession.status}
                    </span>
                  </div>
                </div>

                {/* Messages */}
                <div
                  ref={containerRef}
                  onScroll={handleScroll}
                  className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6 min-h-0 scrollbar-thin"
                >
                  {loadingHistory ? (
                    <div className="flex-1 flex items-center justify-center">
                      <div className="flex flex-col items-center gap-2">
                        <Loader2 className="w-8 h-8 text-accent-cyan animate-spin" />
                        <span className="text-[10px] font-mono text-text-muted uppercase tracking-tighter">
                          loading_history_stream...
                        </span>
                      </div>
                    </div>
                  ) : history && history.all_messages.length > 0 ? (
                    history.all_messages.map((msg, i) => (
                      <div
                        key={i}
                        className={cn(
                          'flex gap-3 md:gap-4 max-w-[90%] md:max-w-[80%]',
                          msg.role === 'user' || msg.role === 'action' ? 'ml-auto flex-row-reverse' : ''
                        )}
                      >
                        <div
                          className={cn(
                            'w-8 h-8 rounded-none shrink-0 flex items-center justify-center border',
                            msg.role === 'user'
                              ? 'bg-accent-purple/5 border-accent-purple/20 text-accent-purple'
                              : msg.role === 'action'
                                ? 'bg-accent-amber/5 border-accent-amber/20 text-accent-amber'
                                : 'bg-accent-cyan/5 border-accent-cyan/20 text-accent-cyan'
                          )}
                        >
                          {msg.role === 'user' ? (
                            <User className="w-4 h-4" />
                          ) : msg.role === 'action' ? (
                            <Clock className="w-4 h-4" />
                          ) : selectedAgent?.picture ? (
                            <img
                              src={`/api/v1/blobs/${selectedAgent.picture}`}
                              alt={selectedAgent.name}
                              className="w-full h-full object-cover"
                            />
                          ) : (
                            <Bot className="w-4 h-4" />
                          )}
                        </div>
                        <div
                          className={cn(
                            'space-y-1 min-w-0',
                            msg.role === 'user' || msg.role === 'action' ? 'text-right' : ''
                          )}
                        >
                          <div
                            className={cn(
                              'p-3 md:p-4 rounded-none text-sm leading-relaxed border font-mono break-all whitespace-pre-wrap max-w-full',
                              msg.role === 'user'
                                ? 'bg-accent-purple/5 border-accent-purple/20 text-text-primary'
                                : msg.role === 'action'
                                  ? 'bg-accent-amber/5 border-accent-amber/20 text-text-muted'
                                  : 'bg-bg-elevated border-border-dim text-text-primary'
                            )}
                          >
                            {msg.content}
                          </div>
                          {/* Audio playback for assistant voice messages */}
                          {msg.role === 'assistant' && msg.audio_url && (
                            <div className="mt-1">
                              <audio
                                controls
                                preload="metadata"
                                src={`/api${msg.audio_url}`}
                                className="w-full h-8 opacity-80 hover:opacity-100 transition-opacity"
                              />
                            </div>
                          )}
                          {/* Action indicator */}
                          {msg.role === 'action' && (
                            <div className="text-[10px] font-mono text-text-muted italic px-3 py-1">
                              ↳ {msg.action_type?.replace(/_/g, ' ')} on {msg.action_id}
                            </div>
                          )}
                          {/* Components inline below assistant message */}
                          {msg.role === 'assistant' && msg.components && msg.components.length > 0 && (
                            <div className="mt-2 space-y-2 max-w-full overflow-x-auto">
                              {msg.components.map((comp: ComponentPayload, ci: number) => (
                                <UiComponentRenderer
                                  key={ci}
                                  payload={comp}
                                  sessionId={activeSessionId || ''}
                                  onAction={handleComponentAction}
                                />
                              ))}
                            </div>
                          )}
                          {/* Attachments inline below assistant message */}
                          {msg.role === 'assistant' && msg.attachments && msg.attachments.length > 0 && (
                            <AttachmentList attachments={msg.attachments} />
                          )}
                          <div
                            className={cn(
                              'flex items-center gap-2 text-[9px] text-text-muted px-1 font-mono uppercase',
                              msg.role === 'user' || msg.role === 'action' ? 'justify-end' : ''
                            )}
                          >
                            <Clock className="w-3 h-3" />
                            {msg.timestamp &&
                              new Date(msg.timestamp).toLocaleTimeString([], {
                                hour12: false,
                              })}
                          </div>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="flex-1 flex flex-col items-center justify-center p-12 text-center">
                      <div className="w-20 h-20 rounded-none bg-bg-elevated border border-border-dim flex items-center justify-center text-text-muted mb-6">
                        <MessageSquare className="w-10 h-10 opacity-10" />
                      </div>
                      <h3 className="text-sm font-mono font-bold text-text-primary mb-2 uppercase tracking-widest">
                        NO_MESSAGES
                      </h3>
                      <p className="text-[10px] font-mono text-text-muted max-w-xs uppercase tracking-tight opacity-70">
                        No messages in this conversation yet.
                      </p>
                    </div>
                  )}

                  {/* Active tool calls */}
                  {toolCalls[activeSessionId || '']?.length > 0 && (
                    <div className="mb-2">
                      <ToolCallBar events={toolCalls[activeSessionId || '']} />
                    </div>
                  )}

                  {/* Streaming draft */}
                  {drafts[activeSessionId || ''] && (
                    <div className="mb-2">
                      <StreamingMessageBubble
                        text={drafts[activeSessionId || '']}
                        agentPicture={selectedAgent?.picture}
                        agentName={selectedAgent?.name}
                      />
                    </div>
                  )}

                  {/* Process trace pane */}
                  {processTraces[activeSessionId || '']?.length > 0 && (
                    <div className="mb-2">
                      <ProcessTracePane events={processTraces[activeSessionId || '']} />
                    </div>
                  )}

                  {activeClient.latestSession.status !== 'ready' &&
                    activeClient.latestSession.status !== 'closed' &&
                    !drafts[activeSessionId || ''] && (
                      <div className="flex gap-4 max-w-[80%]">
                        <div className="w-8 h-8 rounded-none shrink-0 flex items-center justify-center border bg-accent-cyan/5 border-accent-cyan/20 text-accent-cyan overflow-hidden">
                          {selectedAgent?.picture ? (
                            <img
                              src={`/api/v1/blobs/${selectedAgent.picture}`}
                              alt={selectedAgent.name}
                              className="w-full h-full object-cover"
                            />
                          ) : (
                            <Bot className="w-4 h-4" />
                          )}
                        </div>
                        <div className="bg-bg-elevated border border-border-dim p-4 rounded-none flex items-center gap-3">
                          <div className="flex gap-1">
                            <span className="w-1.5 h-1.5 rounded-none bg-accent-cyan animate-pulse" />
                            <span className="w-1.5 h-1.5 rounded-none bg-accent-cyan animate-pulse [animation-delay:0.2s]" />
                            <span className="w-1.5 h-1.5 rounded-none bg-accent-cyan animate-pulse [animation-delay:0.4s]" />
                          </div>
                          <span className="text-[9px] font-mono font-bold text-text-muted uppercase tracking-widest">
                            {lastStatusText[activeSessionId || ''] ||
                              (activeClient.latestSession.status === 'pending_context'
                                ? 'INJECTING_CONTEXT...'
                                : activeClient.latestSession.status === 'agent_processing'
                                  ? 'PROCESSING...'
                                  : 'THINKING...')}
                          </span>
                        </div>
                      </div>
                    )}
                  <div ref={bottomRef} className="h-px w-full shrink-0" />
                </div>

                {/* Scroll indicator */}
                {showScrollIndicator && (
                  <button
                    onClick={() => scrollToBottom('smooth')}
                    className="absolute bottom-28 right-6 md:right-10 z-10 w-10 h-10 rounded-none bg-bg-surface border border-border-dim shadow-xl flex items-center justify-center text-text-muted hover:text-accent-cyan hover:border-accent-cyan transition-all group"
                  >
                    <ArrowDown className="w-5 h-5 group-hover:translate-y-0.5 transition-transform" />
                    {unreadCount > 0 && (
                      <span className="absolute -top-2 -right-2 bg-accent-cyan text-bg-base text-[10px] font-mono font-bold px-1.5 py-0.5 min-w-[20px] text-center border border-bg-base">
                        {unreadCount > 99 ? '99+' : unreadCount}
                      </span>
                    )}
                  </button>
                )}

                {/* Input */}
                <div className="p-4 md:p-6 border-t border-border-dim bg-bg-surface shrink-0">
                  <ChatInput
                    value={messageText}
                    onChange={setMessageText}
                    onSend={handleSendMessage}
                    isPending={sendMessage.isPending}
                    disabled={activeClient.latestSession.status === 'closed'}
                    placeholder={
                      activeClient.latestSession.status === 'closed'
                        ? 'SESSION_CLOSED -- NO INPUT'
                        : 'ENTER COMMAND OR MESSAGE...'
                    }
                    voiceModeEnabled={voiceModeEnabled}
                    onVoiceModeChange={setVoiceModeEnabled}
                  />
                </div>
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center bg-bg-base">
                <div className="flex flex-col items-center gap-2">
                  <Loader2 className="w-8 h-8 text-accent-cyan animate-spin" />
                  <span className="text-[10px] font-mono text-text-muted uppercase tracking-tighter">
                    loading_client_stream...
                  </span>
                </div>
              </div>
            )
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center p-12 text-center bg-bg-base">
              <div className="w-20 h-20 rounded-none bg-bg-elevated border border-border-dim flex items-center justify-center text-text-muted mb-6">
                <MessageCircle className="w-10 h-10 opacity-10" />
              </div>
              <h3 className="text-sm font-mono font-bold text-text-primary mb-2 uppercase tracking-widest">
                SYSTEM_AWAITING_INPUT
              </h3>
              <p className="text-[10px] font-mono text-text-muted max-w-xs uppercase tracking-tight opacity-70">
                Select an agent and channel to view conversations, then choose a client from the list.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
