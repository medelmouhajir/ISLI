import { type CostDashboard } from '@/types'
import { DollarSign, TrendingUp, Users, ListTodo } from 'lucide-react'
import { cn } from '@/lib/utils'

interface CostPanelProps {
  cost: CostDashboard | null
}

export function CostPanel({ cost }: CostPanelProps) {
  if (!cost) {
    return (
      <div className="p-4">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="w-4 h-4 text-accent-amber" />
          <h2 className="text-xs font-display font-semibold uppercase tracking-widest text-text-secondary">
            Telemetry
          </h2>
        </div>
        <div className="text-xs text-text-muted animate-pulse text-center py-6">
          Loading telemetry data...
        </div>
      </div>
    )
  }

  return (
    <div className="p-4">
      <div className="flex items-center gap-2 mb-4">
        <TrendingUp className="w-4 h-4 text-accent-amber" />
        <h2 className="text-xs font-display font-semibold uppercase tracking-widest text-text-secondary">
          Telemetry
        </h2>
      </div>

      <div className="space-y-3">
        {/* Stat tiles */}
        <div className="grid grid-cols-2 gap-2">
          <MetricTile
            icon={<Users className="w-3.5 h-3.5" />}
            label="Agents"
            value={cost.total_agents}
            color="text-accent-cyan"
          />
          <MetricTile
            icon={<ListTodo className="w-3.5 h-3.5" />}
            label="Tasks"
            value={cost.total_tasks}
            color="text-accent-amber"
          />
        </div>

        {/* Spend card */}
        <div
          className={cn(
            'rounded-xl p-3.5 border border-border-dim bg-bg-surface',
            'hover:border-border-bright hover:shadow-card transition-all duration-200'
          )}
        >
          <div className="flex items-center gap-2 mb-1.5">
            <DollarSign className="w-3.5 h-3.5 text-accent-green" />
            <span className="text-[10px] font-display uppercase tracking-wider text-text-secondary">
              Total Spend
            </span>
          </div>
          <div className="font-mono-data text-2xl font-semibold text-accent-green text-glow-green">
            ${cost.total_cost_usd.toFixed(4)}
          </div>
        </div>

        {/* Avg card */}
        <div
          className={cn(
            'rounded-xl p-3.5 border border-border-dim bg-bg-surface',
            'hover:border-border-bright hover:shadow-card transition-all duration-200'
          )}
        >
          <div className="flex items-center gap-2 mb-1.5">
            <TrendingUp className="w-3.5 h-3.5 text-accent-cyan" />
            <span className="text-[10px] font-display uppercase tracking-wider text-text-secondary">
              Avg / Agent
            </span>
          </div>
          <div className="font-mono-data text-lg font-semibold text-accent-cyan">
            ${cost.avg_cost_per_agent.toFixed(4)}
          </div>
        </div>

        {/* Per-agent breakdown */}
        {cost.agent_costs.length > 0 && (
          <div className="pt-2 border-t border-border-dim space-y-2">
            <span className="text-[10px] font-display uppercase tracking-wider text-text-muted">
              Per Agent
            </span>
            {cost.agent_costs.map((c) => (
              <div
                key={c.agent_id}
                className="flex items-center justify-between text-[11px] py-1 px-2 rounded-lg hover:bg-bg-elevated transition-colors"
              >
                <span className="text-text-secondary truncate max-w-[130px] font-mono-data">
                  {c.agent_id}
                </span>
                <span className="font-mono-data text-text-primary font-semibold">
                  ${c.cost_usd.toFixed(4)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function MetricTile({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode
  label: string
  value: number
  color: string
}) {
  return (
    <div
      className={cn(
        'rounded-xl p-3 border border-border-dim bg-bg-surface',
        'hover:border-border-bright hover:shadow-card transition-all duration-200'
      )}
    >
      <div className={cn('flex items-center gap-1.5 mb-1.5', color)}>
        {icon}
        <span className="text-[10px] font-display uppercase tracking-wider opacity-80">
          {label}
        </span>
      </div>
      <div className="font-mono-data text-xl font-semibold text-text-primary">
        {value}
      </div>
    </div>
  )
}
