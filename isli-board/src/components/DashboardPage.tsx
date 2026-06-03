import { useMemo } from 'react'
import {
  Activity,
  Bot,
  BrainCircuit,
  Coins,
  Layers,
  Terminal,
} from 'lucide-react'
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
} from 'recharts'
import { useTasks } from '@/hooks/useTasks'
import { useAgents } from '@/hooks/useAgents'
import { useCostDashboard } from '@/hooks/useCostDashboard'
import { useKeeperDashboard } from '@/hooks/useKeeperDashboard'
import { useTheme } from '@/hooks/useTheme'
import { cn } from '@/lib/utils'

export function DashboardPage() {
  const { data: tasks = [] } = useTasks()
  const { data: agents = [] } = useAgents()
  const { data: cost } = useCostDashboard()
  const { data: keeper } = useKeeperDashboard()
  const { theme } = useTheme()

  const isDark = theme === 'dark'

  // Industrial Signal Tokens (Theme Aware)
  const SIGNALS = {
    healthy: isDark ? '#C6FF4A' : '#16a34a', // Acid Lime (Dark) vs Success Green (Light)
    warning: isDark ? '#FFB800' : '#d97706', // Safety Orange (Dark) vs Amber (Light)
    error: isDark ? '#FF3B30' : '#dc2626',   // High-Vis Red
    info: isDark ? '#22d3ee' : '#0284c7',    // Cyan vs Blue
  }

  const taskStats = useMemo(() => {
    const stats = {
      pending: tasks.filter((t) => t.status === 'pending').length,
      running: tasks.filter((t) => t.status === 'running').length,
      completed: tasks.filter((t) => t.status === 'completed').length,
      failed: tasks.filter((t) => t.status === 'failed').length,
    }
    return [
      { name: 'Pending', value: stats.pending, color: SIGNALS.warning },
      { name: 'Running', value: stats.running, color: SIGNALS.info },
      { name: 'Done', value: stats.completed, color: SIGNALS.healthy },
      { name: 'Fail', value: stats.failed, color: SIGNALS.error },
    ]
  }, [tasks, SIGNALS])

  const formatUptime = (seconds: number) => {
    if (!seconds) return '0s'
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    const s = Math.floor(seconds % 60)
    if (h > 0) return `${h}h ${m}m ${s}s`
    if (m > 0) return `${m}m ${s}s`
    return `${s}s`
  }

  return (
    <div className="flex-1 overflow-auto bg-bg-base p-6 font-mono transition-colors duration-300">
      <div className="max-w-7xl mx-auto space-y-8">
        {/* Header */}
        <div className="flex items-end justify-between border-b border-border-dim pb-4">
          <div>
            <h1 className="text-3xl font-bold text-text-primary tracking-tighter uppercase">
              System Command Center
            </h1>
            <p className="text-[10px] text-accent-green mt-1 tracking-[0.3em] uppercase font-bold">
              ISLI // Autonomous Agent Orchestration // Live Telemetry
            </p>
          </div>
          <div className="text-right hidden sm:block">
            <div className="text-[10px] text-text-muted uppercase tracking-widest font-bold">Node Uptime</div>
            <div className="text-xl text-text-primary font-bold tabular-nums">
              {formatUptime(keeper?.health?.uptime_seconds || 0)}
            </div>
          </div>
        </div>

        {/* KPI Row */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard
            label="Blackboard Load"
            value={tasks.length}
            icon={<Layers className="w-4 h-4" />}
            trend={`${tasks.filter(t => t.status === 'running').length} active tasks`}
            color={SIGNALS.info}
          />
          <MetricCard
            label="Agent Swarm"
            value={agents.filter(a => a.status === 'online').length}
            icon={<Bot className="w-4 h-4" />}
            trend={`${agents.length} registered units`}
            color={SIGNALS.healthy}
          />
          <MetricCard
            label="Resource Burn"
            value={`$${(cost?.total_cost_usd || 0).toFixed(4)}`}
            icon={<Coins className="w-4 h-4" />}
            trend={`${cost?.total_tasks || 0} unit cycles`}
            color={SIGNALS.warning}
          />
          <MetricCard
            label="Keeper Latency"
            value={`${(keeper?.stats?.avg_latency_ms || 0).toFixed(0)}ms`}
            icon={<BrainCircuit className="w-4 h-4" />}
            trend={keeper?.health?.status === 'ready' ? 'NOMINAL' : 'DEGRADED'}
            color={keeper?.health?.status === 'ready' ? SIGNALS.healthy : SIGNALS.warning}
          />
        </div>

        {/* Middle Section: Distribution & Pulse */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Section label="Task State Distribution" className="lg:col-span-2">
            <div className="h-64 mt-4">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={taskStats} layout="vertical" margin={{ left: 0, right: 40, top: 20 }}>
                  <XAxis type="number" hide />
                  <YAxis
                    dataKey="name"
                    type="category"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: isDark ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.5)', fontSize: 10, fontWeight: 'bold' }}
                    width={80}
                  />
                  <Tooltip
                    cursor={{ fill: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)' }}
                    contentStyle={{
                      backgroundColor: isDark ? '#000' : '#fff',
                      border: `1px solid ${isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)'}`,
                      fontSize: '10px',
                      color: isDark ? '#fff' : '#000',
                      borderRadius: '0px',
                    }}
                  />
                  <Bar dataKey="value" radius={[0, 2, 2, 0]} barSize={24}>
                    {taskStats.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Section>

          <Section label="Service Pulse">
            <div className="space-y-4 mt-6">
              <ServiceStatusItem
                label="Core API"
                status="nominal"
                sub="FastAPI Gateway // PORT 8000"
                color={SIGNALS.healthy}
              />
              <ServiceStatusItem
                label="Blackboard"
                status="nominal"
                sub="Redis Task Bus // PORT 6379"
                color={SIGNALS.healthy}
              />
              <ServiceStatusItem
                label="Keeper LMM"
                status={keeper?.health?.status === 'ready' ? 'nominal' : 'degraded'}
                sub={`${keeper?.identity?.default_gen_model || 'Local Model'} // ${keeper?.identity?.ollama_host || '11434'}`}
                color={keeper?.health?.status === 'ready' ? SIGNALS.healthy : SIGNALS.warning}
              />
              <ServiceStatusItem
                label="Semantic Vault"
                status="nominal"
                sub="ChromaDB / Vector Index"
                color={SIGNALS.healthy}
              />
              <ServiceStatusItem
                label="Memory Ledger"
                status="nominal"
                sub="PostgreSQL / Audit Log"
                color={SIGNALS.healthy}
              />
            </div>
          </Section>
        </div>

        {/* Bottom Section: Inference Log & Identity */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Section label="Latest Inference telemetry">
            <div className="mt-4 overflow-hidden border border-border-dim bg-bg-surface/30">
              <table className="w-full text-[10px] text-left border-collapse">
                <thead>
                  <tr className="border-b border-border-dim bg-bg-elevated/50">
                    <th className="p-2 uppercase text-text-muted font-bold">Agent_ID</th>
                    <th className="p-2 uppercase text-text-muted font-bold">Model_Target</th>
                    <th className="p-2 uppercase text-text-muted font-bold text-right">Latency</th>
                    <th className="p-2 uppercase text-text-muted font-bold text-right">Tokens</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-dim/50 tabular-nums text-text-secondary">
                  {keeper?.recent_inferences?.slice(0, 6).map((inf, i) => (
                    <tr key={i} className="hover:bg-bg-elevated/30 transition-colors">
                      <td className="p-2 font-bold text-text-primary truncate max-w-[120px]">{inf.agent_id}</td>
                      <td className="p-2 truncate max-w-[120px]">{inf.model}</td>
                      <td className="p-2 text-right font-bold" style={{ color: SIGNALS.healthy }}>{inf.latency_ms.toFixed(0)}ms</td>
                      <td className="p-2 text-right">{ (inf.tokens_in || 0) + (inf.tokens_out || 0) }</td>
                    </tr>
                  ))}
                  {(!keeper?.recent_inferences || keeper.recent_inferences.length === 0) && (
                    <tr>
                      <td colSpan={4} className="p-8 text-center text-text-muted uppercase tracking-[0.2em]">Idle // Waiting for activity</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Section>

          <Section label="Keeper Identity">
             <div className="grid grid-cols-1 gap-4 mt-4">
               <div className="bg-bg-surface/50 p-4 border border-border-dim space-y-3">
                 <IdentityRow label="Backend" value={keeper?.identity?.backend || 'Ollama'} />
                 <IdentityRow label="Gen Model" value={keeper?.identity?.default_gen_model || '—'} />
                 <IdentityRow label="Embed Model" value={keeper?.identity?.default_embed_model || '—'} />
                 <IdentityRow label="Context" value={`${keeper?.identity?.model_info?.context_length || 4096} tokens`} />
                 <IdentityRow label="Quant" value={keeper?.identity?.model_info?.quantization || '—'} />
               </div>
               <div className="flex items-center gap-3 p-3 border border-border-dim bg-bg-elevated/20">
                 <div className="w-10 h-10 border border-border-dim flex items-center justify-center text-text-primary">
                   <Terminal className="w-5 h-5" />
                 </div>
                 <div className="flex-1">
                   <div className="text-[9px] text-text-muted uppercase font-bold">System Status</div>
                   <div className="text-[11px] text-text-primary uppercase font-bold tracking-widest">
                     Ready for orchestration
                   </div>
                 </div>
                 <Activity className="w-4 h-4 animate-pulse" style={{ color: SIGNALS.healthy }} />
               </div>
             </div>
          </Section>
        </div>
      </div>
    </div>
  )
}

function MetricCard({ label, value, trend, icon, color }: any) {
  return (
    <div
      className={cn(
        "bg-bg-surface/40 border-l border-border-dim p-4 transition-all hover:bg-bg-surface/60 group",
      )}
      style={{ borderLeftColor: color }}
    >
      <div className="flex items-start justify-between">
        <div className="text-[10px] text-text-muted uppercase font-bold tracking-widest group-hover:text-text-secondary transition-colors">
          {label}
        </div>
        <div className="text-text-muted group-hover:text-text-secondary transition-colors">{icon}</div>
      </div>
      <div className="mt-2 text-3xl font-bold text-text-primary tabular-nums tracking-tighter">
        {value}
      </div>
      <div className="mt-1 text-[9px] uppercase tracking-wider font-bold" style={{ color: color }}>
        {trend}
      </div>
    </div>
  )
}

function Section({ label, children, className }: any) {
  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex items-center gap-2">
        <div className="h-3 w-0.5 bg-accent-green" />
        <h2 className="text-[10px] font-bold text-text-primary uppercase tracking-[0.25em]">
          {label}
        </h2>
      </div>
      <div className="bg-bg-surface/20 border border-border-dim p-4 relative overflow-hidden">
        {children}
      </div>
    </div>
  )
}

function ServiceStatusItem({ label, status, sub, color }: any) {
  const isHealthy = status === 'nominal'
  return (
    <div className="flex items-center justify-between group border-b border-border-dim/50 pb-3 last:border-0 last:pb-0">
      <div className="space-y-0.5">
        <div className="text-[10px] font-bold text-text-primary uppercase tracking-wider">{label}</div>
        <div className="text-[8px] text-text-muted uppercase font-bold">{sub}</div>
      </div>
      <div className="flex items-center gap-3">
        <div className="text-[9px] font-bold uppercase tracking-widest" style={{ color }}>{status}</div>
        <div
          className="w-2 h-2 rounded-full"
          style={{
            backgroundColor: color,
            boxShadow: isHealthy ? `0 0 10px ${color}` : 'none',
          }}
        />
      </div>
    </div>
  )
}

function IdentityRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-[10px] uppercase">
      <span className="text-text-muted font-bold tracking-widest">{label}</span>
      <span className="text-text-primary font-bold">{value}</span>
    </div>
  )
}
