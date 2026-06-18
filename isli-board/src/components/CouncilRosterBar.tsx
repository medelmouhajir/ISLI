import { useState } from 'react'
import { cn } from '@/lib/utils'
import { Bot, Plus, X, ChevronDown } from 'lucide-react'
import type { Agent } from '@/types'

interface CouncilRosterBarProps {
  agents: Agent[]
  roomAgentIds: string[]
  addressedAgentIds: string[]
  onAddressedChange: (ids: string[]) => void
  onAddAgent: (agentId: string) => void
}

export function CouncilRosterBar({
  agents,
  roomAgentIds,
  addressedAgentIds,
  onAddressedChange,
  onAddAgent,
}: CouncilRosterBarProps) {
  const [pickerOpen, setPickerOpen] = useState(false)
  const roomAgents = agents.filter((a) => roomAgentIds.includes(a.id))
  const availableAgents = agents.filter((a) => !roomAgentIds.includes(a.id))

  return (
    <div className="flex flex-wrap items-center gap-2 px-3 py-2 border-b border-border-dim/50 bg-bg-elevated/20">
      <span className="text-[10px] uppercase tracking-wider text-text-muted font-display">
        Roster:
      </span>

      {roomAgents.map((agent) => {
        const isAddressed = addressedAgentIds.includes(agent.id)
        return (
          <button
            key={agent.id}
            onClick={() => {
              if (isAddressed) {
                onAddressedChange(addressedAgentIds.filter((id) => id !== agent.id))
              } else {
                onAddressedChange([...addressedAgentIds, agent.id])
              }
            }}
            className={cn(
              'flex items-center gap-1.5 px-2.5 py-1 text-xs font-display border transition-colors',
              isAddressed
                ? 'bg-accent-cyan/10 border-accent-cyan/30 text-accent-cyan'
                : 'bg-bg-surface border-border-dim text-text-secondary hover:border-accent-cyan/40 hover:text-text-primary'
            )}
            title={isAddressed ? 'Click to un-address' : 'Click to address'}
          >
            <div
              className={cn(
                'w-1.5 h-1.5 rounded-full',
                agent.status === 'online' && 'bg-accent-green',
                agent.status === 'paused' && 'bg-accent-amber',
                agent.status === 'offline' && 'bg-accent-red',
                agent.status === 'registered' && 'bg-accent-cyan'
              )}
            />
            <span className="truncate max-w-[120px]">{agent.name}</span>
            {isAddressed && <X className="w-3 h-3" />}
          </button>
        )
      })}

      {availableAgents.length > 0 && (
        <div className="relative">
          <button
            onClick={() => setPickerOpen((v) => !v)}
            className={cn(
              'flex items-center gap-1 px-2.5 py-1 text-xs font-display',
              'bg-bg-surface border border-border-dim text-text-secondary',
              'hover:border-accent-cyan hover:text-accent-cyan transition-colors'
            )}
          >
            <Plus className="w-3 h-3" />
            Agent
            <ChevronDown className="w-3 h-3" />
          </button>
          {pickerOpen && (
            <div className="absolute top-full left-0 mt-1 w-48 bg-bg-elevated border border-border-dim shadow-xl z-50 max-h-60 overflow-y-auto">
              {availableAgents.map((agent) => (
                <button
                  key={agent.id}
                  onClick={() => {
                    onAddAgent(agent.id)
                    setPickerOpen(false)
                  }}
                  className="w-full text-left px-3 py-2 text-sm text-text-secondary hover:bg-accent-cyan/10 hover:text-accent-cyan flex items-center gap-2"
                >
                  <Bot className="w-4 h-4" />
                  {agent.name}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {pickerOpen && (
        <div className="fixed inset-0 z-40" onClick={() => setPickerOpen(false)} />
      )}
    </div>
  )
}
