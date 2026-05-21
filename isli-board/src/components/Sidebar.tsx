import { Link, useLocation } from 'react-router-dom'
import type { Agent, CostDashboard } from '@/types'
import { cn } from '@/lib/utils'
import { AgentsPanel } from './AgentsPanel'
import { CostPanel } from './CostPanel'
import { Cpu, ChevronLeft, ChevronRight, X, LayoutGrid, MessageSquare, BrainCircuit, Bot, FolderGit2 } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

interface SidebarProps {
  agents: Agent[]
  cost: CostDashboard | null
  collapsed: boolean
  onToggle: () => void
  mobileOpen?: boolean
  onCloseMobile?: () => void
}

export function Sidebar({ agents, cost, collapsed, onToggle, mobileOpen, onCloseMobile }: SidebarProps) {
  const location = useLocation()

  const navItems = [
    { label: 'Board', icon: LayoutGrid, path: '/' },
    { label: 'Agents', icon: Bot, path: '/agents' },
    { label: 'Workspaces', icon: FolderGit2, path: '/workspaces' },
    { label: 'Sessions', icon: MessageSquare, path: '/sessions' },
    { label: 'Keeper', icon: BrainCircuit, path: '/keeper' },
  ]

  return (
    <>
      {/* Desktop / Tablet Sidebar */}
      <aside
        className={cn(
          'relative z-10 border-r border-border-dim bg-bg-surface/70 backdrop-blur-xl',
          'hidden md:flex flex-col transition-all duration-300 ease-out',
          collapsed ? 'w-16' : 'w-72'
        )}
      >
        {/* Collapse toggle */}
        <button
          onClick={onToggle}
          className={cn(
            'absolute -right-3 top-20 z-20',
            'w-6 h-6 rounded-full bg-bg-elevated border border-border-bright',
            'flex items-center justify-center text-text-secondary hover:text-accent-cyan',
            'hover:border-accent-cyan hover:shadow-glow-cyan',
            'transition-all duration-200 cursor-pointer'
          )}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? (
            <ChevronRight className="w-3 h-3" />
          ) : (
            <ChevronLeft className="w-3 h-3" />
          )}
        </button>

        {/* Sidebar Header */}
        <div className={cn(
          'flex items-center border-b border-border-dim',
          collapsed ? 'justify-center py-4 px-2' : 'px-4 py-3.5 gap-2.5'
        )}>
          <div className="relative shrink-0">
            <Cpu className="w-5 h-5 text-accent-cyan" />
            <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-accent-green" />
          </div>
          {!collapsed && (
            <span className="text-sm font-display font-bold tracking-wider text-text-primary">
              ISLI
            </span>
          )}
        </div>

        {/* Navigation */}
        <nav className={cn('p-2 space-y-1', collapsed ? 'flex flex-col items-center' : '')}>
          {navItems.map((item) => {
            const isActive = location.pathname === item.path
            return (
              <Link
                key={item.path}
                to={item.path}
                className={cn(
                  'flex items-center gap-3 px-3 py-2 rounded-xl transition-all duration-200 group',
                  isActive
                    ? 'bg-accent-cyan/10 text-accent-cyan'
                    : 'text-text-secondary hover:bg-bg-elevated hover:text-text-primary'
                )}
                title={collapsed ? item.label : undefined}
              >
                <item.icon className={cn('w-4 h-4', isActive ? 'text-accent-cyan' : 'text-text-muted group-hover:text-text-primary')} />
                {!collapsed && (
                  <span className="text-xs font-display font-bold uppercase tracking-widest">
                    {item.label}
                  </span>
                )}
              </Link>
            )
          })}
        </nav>

        <div className="border-t border-border-dim" />

        {collapsed ? (
          <CollapsedSidebar agents={agents} cost={cost} />
        ) : (
          <div className="flex-1 overflow-y-auto min-h-0">
            <AgentsPanel agents={agents} />
            <CostPanel cost={cost} />
          </div>
        )}
      </aside>

      {/* Mobile Drawer */}
      <AnimatePresence>
        {mobileOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm md:hidden"
              onClick={onCloseMobile}
            />
            <motion.aside
              initial={{ x: '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: '-100%' }}
              transition={{ type: 'spring', damping: 28, stiffness: 320 }}
              className="fixed left-0 top-0 bottom-0 z-50 w-80 bg-bg-surface border-r border-border-dim md:hidden overflow-y-auto"
            >
              <div className="sticky top-0 z-10 flex items-center justify-between px-4 py-3.5 border-b border-border-dim bg-bg-surface/95 backdrop-blur-sm">
                <div className="flex items-center gap-2.5">
                  <div className="relative">
                    <Cpu className="w-5 h-5 text-accent-cyan" />
                    <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-accent-green" />
                  </div>
                  <span className="text-sm font-display font-bold tracking-wider text-text-primary">
                    ISLI
                  </span>
                </div>
                <button
                  onClick={onCloseMobile}
                  className="w-8 h-8 rounded-lg border border-border-dim flex items-center justify-center text-text-secondary hover:text-text-primary hover:border-border-bright hover:bg-bg-elevated transition-colors"
                  aria-label="Close sidebar"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Mobile Navigation */}
              <nav className="p-4 space-y-1">
                {navItems.map((item) => {
                  const isActive = location.pathname === item.path
                  return (
                    <Link
                      key={item.path}
                      to={item.path}
                      onClick={onCloseMobile}
                      className={cn(
                        'flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200',
                        isActive
                          ? 'bg-accent-cyan/10 text-accent-cyan shadow-card'
                          : 'text-text-secondary hover:bg-bg-elevated'
                      )}
                    >
                      <item.icon className="w-5 h-5" />
                      <span className="text-xs font-display font-bold uppercase tracking-widest">
                        {item.label}
                      </span>
                    </Link>
                  )
                })}
              </nav>

              <div className="border-t border-border-dim" />

              <AgentsPanel agents={agents} />
              <CostPanel cost={cost} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  )
}

function CollapsedSidebar({ agents, cost }: { agents: Agent[]; cost: CostDashboard | null }) {
  return (
    <div className="flex-1 flex flex-col items-center pt-8 pb-4 gap-6 min-h-0 overflow-y-auto">
      {/* Agent count */}
      <div className="flex flex-col items-center gap-1.5 group cursor-default">
        <div className="relative">
          <div className="w-8 h-8 rounded-lg bg-bg-elevated border border-border-dim flex items-center justify-center text-accent-cyan">
            <span className="text-xs font-mono-data font-bold">{agents.length}</span>
          </div>
          {agents.some(a => a.status === 'online') && (
            <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-accent-green border-2 border-bg-surface" />
          )}
        </div>
      </div>

      {/* Task count */}
      <div className="flex flex-col items-center gap-1.5">
        <div className="w-8 h-8 rounded-lg bg-bg-elevated border border-border-dim flex items-center justify-center text-accent-amber">
          <span className="text-xs font-mono-data font-bold">{cost?.total_tasks ?? 0}</span>
        </div>
      </div>

      {/* Spend */}
      <div className="flex flex-col items-center gap-1.5">
        <div className="w-8 h-8 rounded-lg bg-bg-elevated border border-border-dim flex items-center justify-center text-accent-green">
          <span className="text-[10px] font-mono-data font-bold">$</span>
        </div>
        <span className="text-[9px] font-mono-data text-accent-green">
          {cost ? cost.total_cost_usd.toFixed(1) : '—'}
        </span>
      </div>

      {/* Divider */}
      <div className="w-6 h-px bg-border-dim" />

      {/* Online agents */}
      <div className="flex flex-col items-center gap-2 w-full px-2">
        {agents.slice(0, 8).map((a) => (
          <div
            key={a.id}
            className="group relative flex items-center justify-center w-full"
          >
            <div
              className={cn(
                'w-2.5 h-2.5 rounded-full transition-all',
                a.status === 'online'
                  ? 'bg-accent-green shadow-[0_0_6px_rgba(0,255,136,0.5)]'
                  : a.status === 'paused'
                  ? 'bg-accent-amber'
                  : 'bg-accent-red'
              )}
              title={a.name}
            />
            {/* Tooltip on hover */}
            <div className="absolute left-full ml-2 px-2 py-1 rounded-md bg-bg-elevated border border-border-dim text-[10px] text-text-secondary font-mono-data whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
              {a.name}
            </div>
          </div>
        ))}
        {agents.length > 8 && (
          <span className="text-[8px] font-mono-data text-text-muted">
            +{agents.length - 8}
          </span>
        )}
      </div>
    </div>
  )
}
