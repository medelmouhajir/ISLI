import { useState } from 'react'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  Legend,
} from 'recharts'
import {
  DollarSign,
  TrendingUp,
  Coins,
  AlertTriangle,
  BarChart3,
  PieChart as PieChartIcon,
  Activity,
  ShieldAlert,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useCostDashboard } from '@/hooks/useCostDashboard'
import { useCostHistory } from '@/hooks/useCostHistory'
import { useCostByTier } from '@/hooks/useCostByTier'
import { useBudgetStatus } from '@/hooks/useBudgetStatus'
import type { CostByTier, BudgetStatus } from '@/types'

const RANGE_OPTIONS = [
  { label: '7d', value: 7 },
  { label: '30d', value: 30 },
  { label: '90d', value: 90 },
]

const TIER_COLORS: Record<string, string> = {
  premium: '#ef4444',
  standard: '#22d3ee',
  local: '#34d399',
}

export function CostAnalyticsPage() {
  const [days, setDays] = useState(7)
  const { data: dashboard } = useCostDashboard()
  const { data: history } = useCostHistory(days)
  const { data: tierData } = useCostByTier()
  const { data: budgets } = useBudgetStatus()

  const totalTokens =
    dashboard?.agent_costs.reduce((sum, a) => sum + (a.tokens || 0), 0) || 0
  const avgCostPerTurn =
    dashboard && dashboard.total_cost_usd > 0 && dashboard.total_tasks > 0
      ? dashboard.total_cost_usd / dashboard.total_tasks
      : 0

  return (
    <div className="flex-1 overflow-auto p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-display font-bold text-text-primary tracking-tight">
              Cost Analytics
            </h1>
            <p className="text-sm text-text-muted mt-1">
              Real-time spend telemetry and budget enforcement
            </p>
          </div>
          <div className="flex items-center gap-1 bg-bg-surface border border-border-dim rounded-lg p-1">
            {RANGE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setDays(opt.value)}
                className={cn(
                  'px-3 py-1.5 text-xs font-display font-semibold rounded-md transition-all',
                  days === opt.value
                    ? 'bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/30'
                    : 'text-text-secondary hover:text-text-primary hover:bg-bg-elevated'
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* KPI Row */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard
            icon={<DollarSign className="w-4 h-4" />}
            label="Total Spend"
            value={`$${(dashboard?.total_cost_usd || 0).toFixed(4)}`}
            color="text-accent-green"
            border="border-accent-green/20"
          />
          <KpiCard
            icon={<Coins className="w-4 h-4" />}
            label="Total Tokens"
            value={totalTokens.toLocaleString()}
            color="text-accent-cyan"
            border="border-accent-cyan/20"
          />
          <KpiCard
            icon={<TrendingUp className="w-4 h-4" />}
            label="Avg Cost / Turn"
            value={`$${avgCostPerTurn.toFixed(6)}`}
            color="text-accent-amber"
            border="border-accent-amber/20"
          />
          <KpiCard
            icon={<ShieldAlert className="w-4 h-4" />}
            label="Budgets Active"
            value={String(budgets?.length || 0)}
            color="text-accent-red"
            border="border-accent-red/20"
          />
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Spend Trend */}
          <div className="lg:col-span-2 rounded-xl border border-border-dim bg-bg-surface p-5">
            <div className="flex items-center gap-2 mb-4">
              <Activity className="w-4 h-4 text-accent-cyan" />
              <h2 className="text-sm font-display font-semibold uppercase tracking-wider text-text-secondary">
                Spend Trend
              </h2>
            </div>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={history || []}>
                  <defs>
                    <linearGradient id="colorCost" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#22d3ee" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                  <XAxis
                    dataKey="date"
                    tick={{ fill: '#9ca3af', fontSize: 11, fontFamily: 'monospace' }}
                    axisLine={{ stroke: '#374151' }}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fill: '#9ca3af', fontSize: 11, fontFamily: 'monospace' }}
                    axisLine={{ stroke: '#374151' }}
                    tickLine={false}
                    tickFormatter={(v: number) => `$${v.toFixed(2)}`}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#111827',
                      border: '1px solid #374151',
                      borderRadius: '8px',
                      fontFamily: 'monospace',
                      fontSize: '12px',
                    }}
                    formatter={(value: any) => [`$${Number(value).toFixed(4)}`, 'Cost']}
                  />
                  <Area
                    type="monotone"
                    dataKey="cost_usd"
                    stroke="#22d3ee"
                    strokeWidth={2}
                    fillOpacity={1}
                    fill="url(#colorCost)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Tier Breakdown */}
          <div className="rounded-xl border border-border-dim bg-bg-surface p-5">
            <div className="flex items-center gap-2 mb-4">
              <PieChartIcon className="w-4 h-4 text-accent-amber" />
              <h2 className="text-sm font-display font-semibold uppercase tracking-wider text-text-secondary">
                Tier Breakdown
              </h2>
            </div>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={tierData || []}
                    dataKey="cost_usd"
                    nameKey="tier"
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={90}
                    stroke="none"
                  >
                    {(tierData || []).map((entry: CostByTier, index: number) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={TIER_COLORS[entry.tier] || '#6b7280'}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#111827',
                      border: '1px solid #374151',
                      borderRadius: '8px',
                      fontFamily: 'monospace',
                      fontSize: '12px',
                    }}
                    formatter={(value: any, name: any) => [
                      `$${Number(value).toFixed(4)}`,
                      String(name),
                    ]}
                  />
                  <Legend
                    verticalAlign="bottom"
                    height={36}
                    iconType="circle"
                    formatter={(value: string) => (
                      <span className="text-xs text-text-secondary font-mono-data capitalize">
                        {value}
                      </span>
                    )}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Agent Leaderboard */}
        <div className="rounded-xl border border-border-dim bg-bg-surface p-5">
          <div className="flex items-center gap-2 mb-4">
            <BarChart3 className="w-4 h-4 text-accent-green" />
            <h2 className="text-sm font-display font-semibold uppercase tracking-wider text-text-secondary">
              Agent Spend Leaderboard
            </h2>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={(dashboard?.agent_costs || [])
                  .slice()
                  .sort((a, b) => b.cost_usd - a.cost_usd)
                  .slice(0, 10)}
                layout="vertical"
                margin={{ left: 24 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" horizontal={false} />
                <XAxis
                  type="number"
                  tick={{ fill: '#9ca3af', fontSize: 11, fontFamily: 'monospace' }}
                  axisLine={{ stroke: '#374151' }}
                  tickLine={false}
                  tickFormatter={(v: number) => `$${v.toFixed(2)}`}
                />
                <YAxis
                  type="category"
                  dataKey="agent_id"
                  tick={{ fill: '#9ca3af', fontSize: 11, fontFamily: 'monospace' }}
                  axisLine={{ stroke: '#374151' }}
                  tickLine={false}
                  width={100}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#111827',
                    border: '1px solid #374151',
                    borderRadius: '8px',
                    fontFamily: 'monospace',
                    fontSize: '12px',
                  }}
                  formatter={(value: any) => [`$${Number(value).toFixed(4)}`, 'Cost']}
                />
                <Bar dataKey="cost_usd" fill="#34d399" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Budget Status Table */}
        <div className="rounded-xl border border-border-dim bg-bg-surface p-5">
          <div className="flex items-center gap-2 mb-4">
            <AlertTriangle className="w-4 h-4 text-accent-red" />
            <h2 className="text-sm font-display font-semibold uppercase tracking-wider text-text-secondary">
              Budget Status
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-dim text-text-muted">
                  <th className="text-left py-2 px-3 font-display uppercase tracking-wider text-[10px]">
                    Scope
                  </th>
                  <th className="text-left py-2 px-3 font-display uppercase tracking-wider text-[10px]">
                    ID
                  </th>
                  <th className="text-left py-2 px-3 font-display uppercase tracking-wider text-[10px]">
                    Token Budget
                  </th>
                  <th className="text-left py-2 px-3 font-display uppercase tracking-wider text-[10px]">
                    USD Budget
                  </th>
                  <th className="text-left py-2 px-3 font-display uppercase tracking-wider text-[10px]">
                    Alert At
                  </th>
                </tr>
              </thead>
              <tbody>
                {budgets && budgets.length > 0 ? (
                  budgets.map((b: BudgetStatus) => {
                    const tokenPct = b.monthly_token_cap
                      ? Math.min((b.token_used / b.monthly_token_cap) * 100, 100)
                      : 0
                    const usdPct = b.monthly_usd_cap
                      ? Math.min((b.usd_used / b.monthly_usd_cap) * 100, 100)
                      : 0
                    return (
                      <tr
                        key={`${b.scope}-${b.scope_id}`}
                        className="border-b border-border-dim/50 hover:bg-bg-elevated transition-colors"
                      >
                        <td className="py-3 px-3">
                          <span
                            className={cn(
                              'inline-flex items-center px-2 py-0.5 rounded text-[10px] font-display uppercase tracking-wider',
                              b.scope === 'user'
                                ? 'bg-accent-cyan/10 text-accent-cyan'
                                : 'bg-accent-amber/10 text-accent-amber'
                            )}
                          >
                            {b.scope}
                          </span>
                        </td>
                        <td className="py-3 px-3 font-mono-data text-text-secondary truncate max-w-[180px]">
                          {b.scope_id}
                        </td>
                        <td className="py-3 px-3">
                          <div className="space-y-1">
                            <div className="flex items-center justify-between text-[10px] text-text-muted">
                              <span>
                                {b.token_used.toLocaleString()} /{' '}
                                {b.monthly_token_cap?.toLocaleString() || '∞'}
                              </span>
                              <span>{tokenPct.toFixed(1)}%</span>
                            </div>
                            <div className="h-1.5 w-32 rounded-full bg-bg-elevated overflow-hidden">
                              <div
                                className={cn(
                                  'h-full rounded-full transition-all',
                                  tokenPct >= b.alert_threshold_pct
                                    ? 'bg-accent-red'
                                    : 'bg-accent-cyan'
                                )}
                                style={{ width: `${tokenPct}%` }}
                              />
                            </div>
                          </div>
                        </td>
                        <td className="py-3 px-3">
                          <div className="space-y-1">
                            <div className="flex items-center justify-between text-[10px] text-text-muted">
                              <span>
                                ${b.usd_used.toFixed(4)} / ${b.monthly_usd_cap?.toFixed(2) || '∞'}
                              </span>
                              <span>{usdPct.toFixed(1)}%</span>
                            </div>
                            <div className="h-1.5 w-32 rounded-full bg-bg-elevated overflow-hidden">
                              <div
                                className={cn(
                                  'h-full rounded-full transition-all',
                                  usdPct >= b.alert_threshold_pct
                                    ? 'bg-accent-red'
                                    : 'bg-accent-green'
                                )}
                                style={{ width: `${usdPct}%` }}
                              />
                            </div>
                          </div>
                        </td>
                        <td className="py-3 px-3 font-mono-data text-text-muted">
                          {b.alert_threshold_pct}%
                        </td>
                      </tr>
                    )
                  })
                ) : (
                  <tr>
                    <td
                      colSpan={5}
                      className="py-8 text-center text-text-muted text-xs"
                    >
                      No budgets configured
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}

function KpiCard({
  icon,
  label,
  value,
  color,
  border,
}: {
  icon: React.ReactNode
  label: string
  value: string
  color: string
  border: string
}) {
  return (
    <div
      className={cn(
        'rounded-xl p-4 border bg-bg-surface transition-all duration-200 hover:shadow-card',
        border,
        'hover:border-border-bright'
      )}
    >
      <div className={cn('flex items-center gap-2 mb-2', color)}>
        {icon}
        <span className="text-[10px] font-display uppercase tracking-wider opacity-80">
          {label}
        </span>
      </div>
      <div className="font-mono-data text-xl font-semibold text-text-primary text-glow-green">
        {value}
      </div>
    </div>
  )
}
