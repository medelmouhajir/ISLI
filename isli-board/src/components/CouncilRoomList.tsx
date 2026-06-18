import { useState } from 'react'
import { cn } from '@/lib/utils'
import { Users, Plus, Loader2, MessageSquare, Trash2 } from 'lucide-react'
import type { Room, Agent } from '@/types'
import { formatDistanceToNow } from 'date-fns'

interface CouncilRoomListProps {
  rooms: Room[]
  agents: Agent[]
  selectedRoomId: string | null
  onSelect: (roomId: string) => void
  onCreate: (name: string, agentIds: string[]) => void
  onClose: (roomId: string) => void
  isCreating: boolean
}

export function CouncilRoomList({
  rooms,
  agents,
  selectedRoomId,
  onSelect,
  onCreate,
  onClose,
  isCreating,
}: CouncilRoomListProps) {
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [selectedAgentIds, setSelectedAgentIds] = useState<string[]>([])

  const handleCreate = () => {
    if (!newName.trim() || selectedAgentIds.length === 0) return
    onCreate(newName.trim(), selectedAgentIds)
    setNewName('')
    setSelectedAgentIds([])
    setShowCreate(false)
  }

  return (
    <div className="h-full flex flex-col bg-bg-surface overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border-dim bg-bg-elevated/20 shrink-0">
        <div className="flex items-center gap-2">
          <Users className="w-3.5 h-3.5 text-accent-cyan" />
          <span className="text-xs font-display font-bold uppercase tracking-wider text-text-primary">
            Council Rooms
          </span>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          disabled={isCreating}
          className={cn(
            'p-1.5 rounded-none bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/20',
            'hover:bg-accent-cyan/20 transition-colors disabled:opacity-50'
          )}
          title="New room"
        >
          {isCreating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
        </button>
      </div>


      {showCreate && (
        <div className="p-3 border-b border-border-dim/50 bg-bg-elevated/20 space-y-2">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Room name"
            className={cn(
              'w-full px-2 py-1.5 text-xs bg-bg-base border border-border-dim text-text-primary',
              'focus:outline-none focus:border-accent-cyan'
            )}
          />
          <div className="flex flex-wrap gap-1.5">
            {agents.map((agent) => (
              <button
                key={agent.id}
                onClick={() => {
                  setSelectedAgentIds((prev) =>
                    prev.includes(agent.id) ? prev.filter((id) => id !== agent.id) : [...prev, agent.id]
                  )
                }}
                className={cn(
                  'px-2 py-1 text-[10px] font-display border transition-colors',
                  selectedAgentIds.includes(agent.id)
                    ? 'bg-accent-cyan/10 border-accent-cyan/30 text-accent-cyan'
                    : 'bg-bg-surface border-border-dim text-text-secondary hover:border-accent-cyan/40'
                )}
              >
                {agent.name}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCreate}
              disabled={!newName.trim() || selectedAgentIds.length === 0 || isCreating}
              className="flex-1 px-2 py-1.5 text-xs font-display uppercase bg-accent-cyan text-black disabled:opacity-50"
            >
              Create
            </button>
            <button
              onClick={() => setShowCreate(false)}
              className="px-2 py-1.5 text-xs font-display uppercase bg-bg-surface border border-border-dim text-text-secondary hover:text-text-primary"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {rooms.filter(r => r.status === 'active').length === 0 && !showCreate && (
          <div className="flex flex-col items-center justify-center h-32 text-text-muted px-4 text-center">
            <MessageSquare className="w-6 h-6 mb-2 text-text-muted/30" />
            <p className="text-[11px]">No council rooms yet. Create one to chat with multiple agents in parallel.</p>
          </div>
        )}

        {rooms.filter(r => r.status === 'active').map((room) => {
          const lastMsg = room.messages?.[room.messages.length - 1]
          const isActive = room.id === selectedRoomId
          return (
            <button
              key={room.id}
              onClick={() => onSelect(room.id)}
              className={cn(
                'group w-full text-left px-3 py-2.5 border-b border-border-dim/30 transition-colors',
                isActive ? 'bg-accent-cyan/5 border-l-2 border-l-accent-cyan' : 'hover:bg-bg-elevated/30'
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className={cn('text-xs font-display font-bold truncate', isActive ? 'text-accent-cyan' : 'text-text-primary')}>
                  {room.name}
                </span>
              </div>
              <p className="text-[11px] text-text-muted truncate mt-0.5">
                {lastMsg ? lastMsg.content : 'No messages'}
              </p>
              <div className="flex items-center justify-between mt-1">
                <span className="text-[9px] text-text-muted/60">
                  {room.last_activity_at
                    ? formatDistanceToNow(new Date(room.last_activity_at), { addSuffix: true })
                    : 'Just created'}
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    onClose(room.id)
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1 text-text-muted hover:text-accent-red"
                  title="Close room"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
