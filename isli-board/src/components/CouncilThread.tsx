import { useMemo } from 'react'
import { cn } from '@/lib/utils'
import { User, Activity } from 'lucide-react'
import type { Agent, Room, RoomMessage } from '@/types'
import { CouncilResponseCard } from './CouncilResponseCard'

interface CouncilThreadProps {
  room: Room
  agents: Agent[]
  activeAgentIds: string[]
  streamingAgentIds: string[]
  pendingAddressedIds?: string[] | null
  pinnedMessageIds: string[]
  onPin: (messageId: string) => void
  onUnpin: (messageId: string) => void
  onComponentAction?: (
    sessionId: string,
    actionId: string,
    actionType: string,
    payload: Record<string, unknown>
  ) => void
}

interface ThreadGroup {
  parentId: string
  userMessage: RoomMessage
  replies: Record<string, RoomMessage>
}

export function CouncilThread({
  room,
  agents,
  activeAgentIds,
  streamingAgentIds,
  pendingAddressedIds,
  pinnedMessageIds,
  onPin,
  onUnpin,
  onComponentAction,
}: CouncilThreadProps) {
  const groups = useMemo(() => {
    const list: ThreadGroup[] = []
    const map = new Map<string, ThreadGroup>()

    for (const msg of room.messages || []) {
      if (msg.role === 'system') continue
      
      if (msg.role === 'user') {
        const group: ThreadGroup = {
          parentId: msg.id,
          userMessage: msg,
          replies: {},
        }
        list.push(group)
        map.set(msg.id, group)
      } else if (msg.role === 'assistant' && msg.agent_id) {
        let group = msg.parent_id ? map.get(msg.parent_id) : undefined
        if (!group && list.length > 0) {
          group = list[list.length - 1]
        }
        if (group) {
          group.replies[msg.agent_id] = msg
        }
      }
    }

    return list
  }, [room.messages])

  const activeAgents = agents.filter((a) => activeAgentIds.includes(a.id))
  const lastAddressedIds = (room.room_metadata?.last_addressed_agent_ids as string[]) || []

  return (
    <div className="flex-1 overflow-y-auto custom-scrollbar p-3 md:p-6 space-y-12">
      {groups.length === 0 && (
        <div className="flex flex-col items-center justify-center h-full text-text-muted">
          <div className="w-16 h-16 bg-bg-surface border border-border-dim flex items-center justify-center mb-4">
            <Activity className="w-8 h-8 text-accent-cyan/20" />
          </div>
          <p className="text-[10px] font-display uppercase tracking-[0.3em]">System Idle // Waiting for Command</p>
        </div>
      )}

      {groups.map((group, groupIndex) => {
        const isLatestGroup = groupIndex === groups.length - 1
        const addressedForGroup = isLatestGroup
          ? pendingAddressedIds ?? (lastAddressedIds.length > 0 ? lastAddressedIds : activeAgentIds)
          : []

        const respondingAgents = activeAgents.filter((agent) => {
          const reply = group.replies[agent.id] || null
          const hasReply = !!reply
          const isStreaming = isLatestGroup && streamingAgentIds.includes(agent.id) && !hasReply
          const isAddressed = addressedForGroup.includes(agent.id)
          return hasReply || isStreaming || isAddressed
        })

        return (
          <div key={group.parentId} className="relative group/thread">
            {/* Vertical Rail */}
            <div className="absolute left-[15px] top-8 bottom-[-48px] w-px bg-border-dim/30 last:hidden" />

            <div className="space-y-6">
              {/* User Prompt (Operator Signal) */}
              <div className="flex items-start gap-4">
                <div className="w-8 h-8 bg-accent-cyan text-black flex items-center justify-center shrink-0 z-10">
                  <User className="w-5 h-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-[10px] font-display font-bold uppercase tracking-widest text-accent-cyan">
                      OPERATOR_SIGNAL
                    </span>
                    <span className="text-[9px] font-display text-text-muted/40 uppercase tracking-tighter">
                      [{new Date(group.userMessage.timestamp).toISOString()}]
                    </span>
                  </div>
                  <p className="text-sm md:text-base text-text-primary whitespace-pre-wrap leading-relaxed font-mono opacity-90">
                    {group.userMessage.content}
                  </p>
                </div>
              </div>

              {/* Agent Response Grid */}
              {respondingAgents.length > 0 && (
                <div className="pl-12">
                  <div
                    className={cn(
                      'grid gap-4',
                      respondingAgents.length === 1 && 'grid-cols-1',
                      respondingAgents.length === 2 && 'lg:grid-cols-2 grid-cols-1',
                      respondingAgents.length === 3 && 'lg:grid-cols-3 grid-cols-1',
                      respondingAgents.length >= 4 && 'lg:grid-cols-2 grid-cols-1'
                    )}
                  >
                    {respondingAgents.map((agent) => {
                      const reply = group.replies[agent.id] || null
                      const isStreaming = isLatestGroup && streamingAgentIds.includes(agent.id) && !reply
                      const isPinned = reply ? pinnedMessageIds.includes(reply.id) : false
                      return (
                        <CouncilResponseCard
                          key={agent.id}
                          agent={agent}
                          roomId={room.id}
                          message={reply}
                          isStreaming={isStreaming}
                          isPinned={isPinned}
                          onPin={() => reply && onPin(reply.id)}
                          onUnpin={() => reply && onUnpin(reply.id)}
                          onAction={
                            onComponentAction
                              ? (actionId, actionType, payload) =>
                                  onComponentAction(`room:${room.id}:${agent.id}`, actionId, actionType, payload)
                              : undefined
                          }
                        />
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
