import { useState, useEffect, useMemo } from 'react'
import { ArrowLeft, Loader2, X, Clock } from 'lucide-react'
import type { Agent, Room } from '@/types'
import { CouncilRosterBar } from './CouncilRosterBar'
import { CouncilThread } from './CouncilThread'
import { CouncilInput } from './CouncilInput'
import { useBoardSocket } from '@/hooks/useBoardSocket'

interface CouncilRoomProps {
  room: Room
  agents: Agent[]
  onBack?: () => void
  onAddAgent: (agentId: string) => void
  onSendMessage: (text: string, addressedAgentIds?: string[]) => void
  onClose: () => void
  onPin: (messageId: string) => void
  onUnpin: (messageId: string) => void
  onShowHistory?: () => void
  onComponentAction?: (
    sessionId: string,
    actionId: string,
    actionType: string,
    payload: Record<string, unknown>
  ) => void
  isSending: boolean
  isAddingAgent: boolean
  isClosing: boolean
}

export function CouncilRoom({
  room,
  agents,
  onBack,
  onAddAgent,
  onSendMessage,
  onClose,
  onPin,
  onUnpin,
  onShowHistory,
  onComponentAction,
  isSending,
  isAddingAgent,
  isClosing,
}: CouncilRoomProps) {
  const { lastMessage } = useBoardSocket()
  // Addressed agents are driven by explicit user selection and by @mentions
  // parsed live in CouncilInput. We intentionally do NOT default to the full
  // room roster or the sticky last_addressed set here, so that a message like
  // "@harvey hi" dispatches to Harvey only.
  const [addressedAgentIds, setAddressedAgentIds] = useState<string[]>([])
  const [streamingAgentIds, setStreamingAgentIds] = useState<string[]>([])
  // Snapshot of the addressed set at the moment the latest message was sent.
  // This lets CouncilThread show the right in-flight cards before the backend
  // refreshes room.room_metadata.last_addressed_agent_ids.
  const [pendingAddressedIds, setPendingAddressedIds] = useState<string[] | null>(null)

  // Track streaming agents from session:updated events (pending_context / agent_processing)
  useEffect(() => {
    if (!lastMessage) return
    if (lastMessage.type === 'session:updated') {
      const { session_id, status } = lastMessage.payload || {}
      if (!session_id) return
      
      // Match room session ID pattern: room:{room_id}:{agent_id}
      const parts = session_id.split(':')
      if (parts[0] === 'room' && parts[1] === room.id) {
        const agentId = parts[2]
        if (!agentId) return
        
        if (status === 'agent_processing' || status === 'pending_context' || status === 'processing_context') {
          setStreamingAgentIds((prev) => (prev.includes(agentId) ? prev : [...prev, agentId]))
        } else if (status === 'ready' || status === 'closed') {
          setStreamingAgentIds((prev) => prev.filter((id) => id !== agentId))
        }
      }
    }
    if (lastMessage.type === 'room:updated') {
      const { room_id } = lastMessage.payload || {}
      if (room_id === room.id) {
        // We can't clear all streaming immediately on room:updated because 
        // multiple agents might be replying. But we can trigger a refresh.
      }
    }
  }, [lastMessage, room.id])

  const pinnedMessageIds = useMemo(
    () => (room.pins || []).map((p) => p.message_id),
    [room.pins]
  )

  const handleSend = (text: string) => {
    // Clear streaming states when user sends a new message to avoid UI ghosting
    setStreamingAgentIds([])
    // Remember who we addressed so the thread can render the right response
    // sections immediately, before the backend round-trip completes.
    setPendingAddressedIds([...addressedAgentIds])
    onSendMessage(text, addressedAgentIds)
  }

  // Once the room has caught up with a new user message, the backend-provided
  // last_addressed_agent_ids is authoritative; drop the local snapshot.
  const lastAddressedIds = (room.room_metadata?.last_addressed_agent_ids as string[]) || []
  useEffect(() => {
    if (!pendingAddressedIds) return
    // If the last addressed set has changed, the backend has processed the send.
    const sameLength = pendingAddressedIds.length === lastAddressedIds.length
    const sameSet = sameLength && pendingAddressedIds.every((id) => lastAddressedIds.includes(id))
    if (!sameSet) {
      setPendingAddressedIds(null)
    }
  }, [lastAddressedIds, pendingAddressedIds])

  const hasMessages = (room.messages || []).some(m => m.role !== 'system')

  return (
    <div className="h-full flex flex-col bg-bg-base/50 relative overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border-dim/50 bg-bg-elevated/20 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <button
            onClick={onShowHistory}
            className="p-1.5 text-text-muted hover:text-accent-cyan transition-colors"
            title="Access History"
          >
            <Clock className="w-4 h-4" />
          </button>
          {onBack && (
            <button
              onClick={onBack}
              className="md:hidden p-1.5 text-text-muted hover:text-text-primary"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
          )}
          <h2 className="text-sm font-display font-bold text-text-primary truncate">
            {room.name}
          </h2>
          {isClosing && <Loader2 className="w-3 h-3 text-accent-cyan animate-spin" />}
        </div>
        <button
          onClick={onClose}
          disabled={isClosing}
          className="flex items-center gap-1 px-2 py-1 text-[10px] font-display uppercase tracking-wider bg-bg-surface border border-border-dim text-text-secondary hover:text-accent-red hover:border-accent-red/30 transition-colors disabled:opacity-50"
        >
          <X className="w-3 h-3" />
          Close
        </button>
      </div>

      <CouncilRosterBar
        agents={agents}
        roomAgentIds={room.agent_ids || []}
        addressedAgentIds={addressedAgentIds}
        onAddressedChange={setAddressedAgentIds}
        onAddAgent={onAddAgent}
      />

      <div className="flex-1 overflow-hidden relative flex flex-col">
        {hasMessages ? (
          <>
            <CouncilThread
              room={room}
              agents={agents}
              activeAgentIds={room.agent_ids || []}
              streamingAgentIds={streamingAgentIds}
              pendingAddressedIds={pendingAddressedIds}
              pinnedMessageIds={pinnedMessageIds}
              onPin={onPin}
              onUnpin={onUnpin}
              onComponentAction={onComponentAction}
            />

            <CouncilInput
              agents={agents.filter((a) => (room.agent_ids || []).includes(a.id))}
              addressedAgentIds={addressedAgentIds}
              onAddressedChange={setAddressedAgentIds}
              onSend={handleSend}
              disabled={isSending || isAddingAgent}
              placeholder={addressedAgentIds.length === 0 ? 'Address at least one agent...' : 'Type your message...'}
            />
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center p-6 relative">
            {/* Background elements for heroic centered input */}
            <div className="absolute left-1/2 top-0 bottom-0 w-px bg-border-dim/20 -translate-x-1/2 pointer-events-none" />
            <div className="absolute top-1/2 left-0 right-0 h-px bg-border-dim/10 -translate-y-1/2 pointer-events-none" />
            
            <div className="w-full max-w-2xl relative z-10 space-y-8">
              <div className="text-center space-y-2">
                <div className="inline-flex items-center justify-center w-12 h-12 border border-accent-cyan/30 bg-accent-cyan/5 text-accent-cyan mb-2">
                  <Clock className="w-6 h-6" />
                </div>
                <h3 className="text-xl font-display font-bold text-text-primary uppercase tracking-tight">
                  Initiate Council Session
                </h3>
                <p className="text-[10px] text-text-muted uppercase tracking-[0.2em]">
                  Room: {room.name} // Addressing {addressedAgentIds.length} unit(s)
                </p>
              </div>

              <div className="bg-bg-surface border border-border-dim shadow-2xl p-1">
                <CouncilInput
                  agents={agents.filter((a) => (room.agent_ids || []).includes(a.id))}
                  addressedAgentIds={addressedAgentIds}
                  onAddressedChange={setAddressedAgentIds}
                  onSend={handleSend}
                  disabled={isSending || isAddingAgent}
                  placeholder="Enter initial command for the council..."
                  isHero
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

