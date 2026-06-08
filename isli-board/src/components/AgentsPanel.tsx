import type { Agent } from '@/types'
import { StatusBadge } from './StatusBadge'
import { Bot, Cpu } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Link } from 'react-router-dom'

interface AgentsPanelProps {
  agents: Agent[]
}

export function AgentsPanel({ agents }: AgentsPanelProps) {
  return (
    <div className="p-4 border-b border-border-dim">
      <div className="flex items-center justify-between mb-3">
        <Link 
          to="/agents"
          className="flex items-center gap-2 hover:text-accent-cyan transition-colors"
        >
          <Bot className="w-4 h-4 text-accent-cyan" />
          <h2 className="text-xs font-display font-semibold uppercase tracking-widest text-text-secondary hover:text-accent-cyan">
            Agents
          </h2>
        </Link>
        <span className="text-[10px] px-2 py-0.5 rounded-full bg-bg-elevated text-text-muted font-mono-data border border-border-dim">
          {agents.length}
        </span>
      </div>

      <div className="space-y-1.5">
        {agents.map((a) => (
          <Link
            key={a.id}
            to={`/agents/${a.id}`}
            className={cn(
              'group relative flex items-center gap-3 rounded-xl px-3 py-2.5',
              'bg-bg-surface border border-border-dim',
              'hover:border-accent-cyan hover:bg-bg-elevated hover:shadow-card',
              'transition-all duration-200 cursor-pointer'
            )}
          >
            {/* Avatar dot */}
            <div className="shrink-0 relative">
              <div
                className={cn(
                  'w-8 h-8 rounded-lg flex items-center justify-center overflow-hidden',
                  !a.picture && (
                    a.status === 'online'
                      ? 'bg-accent-green/10 text-accent-green'
                      : a.status === 'paused'
                      ? 'bg-accent-amber/10 text-accent-amber'
                      : 'bg-accent-red/10 text-accent-red'
                  )
                )}
              >
                {a.picture ? (
                  <img 
                    src={`/api/v1/blobs/${a.picture}`} 
                    alt={a.name} 
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <Cpu className="w-4 h-4" />
                )}
              </div>
              <span
                className={cn(
                  'absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-bg-surface',
                  a.status === 'online' && 'bg-accent-green',
                  a.status === 'paused' && 'bg-accent-amber',
                  a.status === 'offline' && 'bg-accent-red',
                  a.status === 'registered' && 'bg-accent-cyan',
                  a.status === 'deleted' && 'bg-text-muted'
                )}
              />
            </div>

            {/* Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-display font-medium text-text-primary truncate group-hover:text-accent-cyan transition-colors">
                  {a.name}
                </span>
              </div>
              <div className="flex items-center gap-2 mt-0.5">
                <StatusBadge status={a.status} />
                <span className="text-[10px] font-mono-data text-text-muted truncate">
                  {a.model_provider || 'no model'}
                </span>
              </div>
              {/* Token bar */}
              <div className="mt-2 flex items-center gap-2">
                <div className="flex-1 h-1 rounded-full bg-bg-elevated overflow-hidden">
                  <div
                    className={cn(
                      'h-full rounded-full transition-all duration-500',
                      a.token_budget && a.token_used / a.token_budget > 0.8
                        ? 'bg-accent-red'
                        : a.token_budget && a.token_used / a.token_budget > 0.5
                        ? 'bg-accent-amber'
                        : 'bg-accent-green'
                    )}
                    style={{
                      width: a.token_budget
                        ? `${Math.min((a.token_used / a.token_budget) * 100, 100)}%`
                        : '0%',
                    }}
                  />
                </div>
                <span className="text-[10px] font-mono-data text-text-muted shrink-0">
                  {a.token_used.toLocaleString()}
                </span>
              </div>
            </div>
          </Link>
        ))}
        {agents.length === 0 && (
          <div className="text-xs text-text-muted text-center py-6 border border-dashed border-border-dim rounded-xl bg-bg-surface/50">
            No agents registered
          </div>
        )}
      </div>
    </div>
  )
}
