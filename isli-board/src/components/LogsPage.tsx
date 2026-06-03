import { useNavigate } from 'react-router-dom'
import { 
  Terminal, 
  ShieldCheck, 
  Database, 
  Cpu, 
  History, 
  Zap 
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface LogCategory {
  id: string
  title: string
  subtitle: string
  description: string
  icon: any
  status: 'streaming' | 'idle' | 'archived'
  metric?: string
  path: string
  color: string
}

const CATEGORIES: LogCategory[] = [
  {
    id: 'agent-execution',
    title: 'EXECUTION.LOG',
    subtitle: 'AGENT REAL-TIME STREAMS',
    description: 'Live stdout/stderr capture from all active autonomous agents.',
    icon: Terminal,
    status: 'streaming',
    metric: 'LIVE',
    path: '/agents',
    color: 'text-accent-cyan'
  },
  {
    id: 'audit-trail',
    title: 'AUDIT.TRAIL',
    subtitle: 'SYSTEM INTEGRITY LOGS',
    description: 'Cryptographically signed records of all system-level state changes.',
    icon: ShieldCheck,
    status: 'archived',
    metric: 'VERIFIED',
    path: '/logs', // Stub
    color: 'text-accent-green'
  },
  {
    id: 'memory-journals',
    title: 'MEMORY.JOURNALS',
    subtitle: 'RAG & STATE TRANSITIONS',
    description: 'Journal diffs for Episodic and Semantic memory hydration events.',
    icon: Database,
    status: 'streaming',
    metric: 'SYNCED',
    path: '/keeper',
    color: 'text-accent-violet'
  },
  {
    id: 'core-services',
    title: 'CORE.SYSTEM',
    subtitle: 'SERVICE HEALTH & HEARTBEAT',
    description: 'Internal logs for isli-core, redis, and postgres telemetry.',
    icon: Cpu,
    status: 'streaming',
    metric: '99.9% UP',
    path: '/logs', // Stub
    color: 'text-accent-amber'
  },
  {
    id: 'task-history',
    title: 'TASK.HISTORY',
    subtitle: 'KANBAN AUDIT TRAIL',
    description: 'Full lifecycle tracking of task transitions and owner handoffs.',
    icon: History,
    status: 'archived',
    metric: 'IMMUTABLE',
    path: '/kanban',
    color: 'text-accent-cyan'
  },
  {
    id: 'gateway-traffic',
    title: 'GATEWAY.LOGS',
    subtitle: 'CHANNEL & I/O TRAFFIC',
    description: 'Inbound/outbound traffic logs for Telegram, Web, and SDK channels.',
    icon: Zap,
    status: 'idle',
    metric: 'SECURE',
    path: '/logs', // Stub
    color: 'text-accent-red'
  }
]

export function LogsPage() {
  const navigate = useNavigate()

  return (
    <main className="flex-1 overflow-y-auto bg-bg-base relative p-6 md:p-10 custom-scrollbar">
      {/* Background decoration - Industrial Ticker */}
      <div className="absolute top-0 right-0 p-4 opacity-10 pointer-events-none hidden lg:block">
        <div className="text-[120px] font-display font-bold leading-none select-none text-text-muted">
          LOGS_INFRA
        </div>
      </div>

      <header className="mb-12 relative z-10">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-2 h-6 bg-accent-cyan" />
          <h1 className="text-3xl font-display font-bold tracking-tighter text-text-primary uppercase">
            System Observability
          </h1>
        </div>
        <p className="text-text-secondary font-mono text-sm max-w-2xl border-l border-border-dim pl-4">
          Centralized diagnostic interface for real-time telemetry, audit trails, and memory journals across the ISLI swarm.
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 relative z-10">
        {CATEGORIES.map((cat, idx) => (
          <button
            key={cat.id}
            onClick={() => navigate(cat.path)}
            className={cn(
              "group relative flex flex-col items-start p-6 text-left",
              "bg-bg-surface border border-border-dim transition-all duration-300",
              "hover:border-accent-cyan hover:shadow-glow-cyan/20",
              "animate-stagger-in"
            )}
            style={{ animationDelay: `${idx * 50}ms` }}
          >
            {/* Index number */}
            <span className="absolute top-4 right-4 text-[10px] font-mono text-text-muted group-hover:text-accent-cyan transition-colors">
              [0{idx + 1}]
            </span>

            <div className={cn("p-3 mb-6 bg-bg-elevated group-hover:bg-accent-cyan/10 transition-colors rounded", cat.color)}>
              <cat.icon className="w-6 h-6" />
            </div>

            <div className="mb-1">
              <h3 className="text-lg font-display font-bold text-text-primary tracking-tight group-hover:text-accent-cyan transition-colors">
                {cat.title}
              </h3>
              <p className="text-[10px] font-mono font-bold tracking-widest text-text-muted uppercase">
                {cat.subtitle}
              </p>
            </div>

            <p className="text-xs text-text-secondary leading-relaxed mb-8 h-12 overflow-hidden line-clamp-3">
              {cat.description}
            </p>

            <div className="mt-auto w-full flex items-center justify-between pt-4 border-t border-border-dim/50">
              <div className="flex items-center gap-2">
                <div className={cn(
                  "w-1.5 h-1.5 rounded-full",
                  cat.status === 'streaming' ? "bg-accent-green animate-pulse" : 
                  cat.status === 'archived' ? "bg-accent-cyan" : "bg-text-muted"
                )} />
                <span className="text-[10px] font-mono font-bold text-text-muted uppercase tracking-wider">
                  {cat.status}
                </span>
              </div>
              
              {cat.metric && (
                <span className={cn(
                  "text-[10px] font-mono font-bold px-2 py-0.5 bg-bg-elevated border border-border-dim",
                  cat.color
                )}>
                  {cat.metric}
                </span>
              )}
            </div>

            {/* Industrial Ticker Decor */}
            <div className="absolute bottom-0 left-0 w-full h-1 overflow-hidden">
               <div className="w-full h-full bg-accent-cyan opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
            
            {/* Scanline effect on hover */}
            <div className="absolute inset-0 pointer-events-none opacity-0 group-hover:opacity-5 transition-opacity bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.25)_50%),linear-gradient(90deg,rgba(255,0,0,0.06),rgba(0,255,0,0.02),rgba(0,0,255,0.06))] bg-[length:100%_2px,3px_100%]" />
          </button>
        ))}
      </div>

      <footer className="mt-16 pt-8 border-t border-border-dim flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div className="flex items-center gap-6">
          <div className="flex flex-col">
            <span className="text-[10px] font-mono text-text-muted uppercase">System Entropy</span>
            <span className="text-sm font-mono-data text-text-primary tracking-tighter">0.0024 BIT/S</span>
          </div>
          <div className="flex flex-col">
            <span className="text-[10px] font-mono text-text-muted uppercase">Buffer Load</span>
            <span className="text-sm font-mono-data text-text-primary tracking-tighter">12.4 MB</span>
          </div>
        </div>
        
        <div className="text-[10px] font-mono text-text-muted uppercase tracking-widest">
          ISLI // OBSERVABILITY_v1.0.4 // STABLE_BUILD
        </div>
      </footer>
    </main>
  )
}
