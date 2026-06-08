import { useAgents } from '@/hooks/useAgents'
import { StatusBadge } from './StatusBadge'
import { Bot, Cpu, Plus, ArrowRight, Zap, Database, Globe } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/Button'

export function AgentsPage() {
  const { data: agents = [], isLoading } = useAgents()

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-base">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-accent-cyan/20 border-t-accent-cyan rounded-full animate-spin" />
          <span className="text-sm font-display font-medium text-text-muted animate-pulse">
            Loading agents...
          </span>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto bg-bg-base p-6 md:p-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-display font-bold text-text-primary flex items-center gap-3">
            <Bot className="w-8 h-8 text-accent-cyan" />
            Agents
          </h1>
          <p className="text-text-secondary mt-1 max-w-xl">
            Manage your autonomous workers, their models, and specialized skills.
          </p>
        </div>
        <Link to="/agents/new">
          <Button className="shadow-glow-cyan w-full md:w-auto">
            <Plus className="w-4 h-4 mr-2" />
            Create Agent
          </Button>
        </Link>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {agents.map((agent) => (
          <Link
            key={agent.id}
            to={`/agents/${agent.id}`}
            className={cn(
              'group flex flex-col p-5 rounded-2xl bg-bg-surface border border-border-dim',
              'hover:border-accent-cyan hover:shadow-card-hover hover:-translate-y-1',
              'transition-all duration-300 relative overflow-hidden'
            )}
          >
            {/* Background decoration */}
            <div className="absolute top-0 right-0 p-8 -mr-8 -mt-8 opacity-[0.03] group-hover:opacity-[0.07] transition-opacity">
              <Bot className="w-32 h-32" />
            </div>

            <div className="flex items-start justify-between mb-4 relative z-10">
              <div className="w-12 h-12 rounded-xl bg-bg-elevated border border-border-dim flex items-center justify-center text-accent-cyan group-hover:border-accent-cyan/50 transition-colors overflow-hidden">
                {agent.picture ? (
                  <img 
                    src={`/api/v1/blobs/${agent.picture}`} 
                    alt={agent.name} 
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <Cpu className="w-6 h-6" />
                )}
              </div>
              <StatusBadge status={agent.status} />
            </div>

            <div className="mb-4 relative z-10">
              <h3 className="text-lg font-display font-bold text-text-primary group-hover:text-accent-cyan transition-colors truncate">
                {agent.name}
              </h3>
              <p className="text-sm text-text-muted line-clamp-2 min-h-[40px] mt-1">
                {agent.description || 'No description provided.'}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4 pt-4 border-t border-border-dim relative z-10">
              <div className="flex flex-col gap-1">
                <span className="text-[10px] font-mono-data text-text-muted uppercase tracking-wider">Model</span>
                <div className="flex items-center gap-1.5 text-xs text-text-secondary">
                  <Zap className="w-3 h-3 text-accent-amber" />
                  <span className="truncate">{agent.model_id || 'Not set'}</span>
                </div>
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-[10px] font-mono-data text-text-muted uppercase tracking-wider">Skills</span>
                <div className="flex items-center gap-1.5 text-xs text-text-secondary">
                  <Database className="w-3 h-3 text-accent-green" />
                  <span>{agent.skills.length} tools</span>
                </div>
              </div>
            </div>

            <div className="mt-6 flex items-center justify-between relative z-10">
              <div className="flex -space-x-2">
                {agent.channels.map((ch) => (
                  <div 
                    key={ch} 
                    className="w-7 h-7 rounded-full bg-bg-elevated border-2 border-bg-surface flex items-center justify-center text-text-secondary"
                    title={ch}
                  >
                    <Globe className="w-3.5 h-3.5" />
                  </div>
                ))}
                {agent.channels.length === 0 && (
                  <span className="text-[10px] text-text-muted italic">No channels</span>
                )}
              </div>
              <div className="text-accent-cyan opacity-0 group-hover:opacity-100 transform translate-x-2 group-hover:translate-x-0 transition-all">
                <ArrowRight className="w-5 h-5" />
              </div>
            </div>

            {/* Progress bar for tokens */}
            <div className="absolute bottom-0 left-0 right-0 h-1 bg-transparent">
               <div 
                className={cn(
                  'h-full transition-all duration-500',
                  agent.token_budget && agent.token_used / agent.token_budget > 0.8
                    ? 'bg-accent-red'
                    : agent.token_budget && agent.token_used / agent.token_budget > 0.5
                    ? 'bg-accent-amber'
                    : 'bg-accent-cyan'
                )}
                style={{
                  width: agent.token_budget
                    ? `${Math.min((agent.token_used / agent.token_budget) * 100, 100)}%`
                    : '0%',
                }}
              />
            </div>
          </Link>
        ))}

        {agents.length === 0 && (
          <div className="col-span-full flex flex-col items-center justify-center py-20 border-2 border-dashed border-border-dim rounded-3xl bg-bg-surface/30">
            <Bot className="w-16 h-16 text-text-muted mb-4 opacity-20" />
            <h3 className="text-xl font-display font-bold text-text-secondary">No Agents Found</h3>
            <p className="text-text-muted mb-8 text-center max-w-xs">
              Start by creating your first specialized agent to handle tasks.
            </p>
            <Link to="/agents/new">
              <Button>
                <Plus className="w-4 h-4 mr-2" />
                Create Agent
              </Button>
            </Link>
          </div>
        )}
      </div>
    </div>
  )
}
