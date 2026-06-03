import { Link, useLocation, useNavigate } from 'react-router-dom'
import type { Agent, CostDashboard } from '@/types'
import { cn } from '@/lib/utils'
import { AgentsPanel } from './AgentsPanel'
import { CostPanel } from './CostPanel'
import { StatusBadge } from './StatusBadge'
import {
  BarChart3,
  ChevronLeft,
  ChevronRight,
  X,
  LayoutGrid,
  MessageSquare,
  MessageCircle,
  BrainCircuit,
  Bot,
  FolderGit2,
  Users,
  Settings,
  Gauge,
  ScrollText,
  Cpu,
  ShoppingBag,
  Newspaper,
} from 'lucide-react'
import { motion, AnimatePresence, animate, useMotionValue, type PanInfo } from 'framer-motion'
import { useState, useEffect, useRef, useCallback } from 'react'

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
    { label: 'Dashboard', icon: Gauge, path: '/' },
    { label: 'Kanban', icon: LayoutGrid, path: '/kanban' },
    { label: 'Agents', icon: Bot, path: '/agents' },
    { label: 'Skills Store', icon: ShoppingBag, path: '/store' },
    { label: 'Workspaces', icon: FolderGit2, path: '/workspaces' },
    { label: 'Shared', icon: Users, path: '/shared-workspaces' },
    { label: 'Sessions', icon: MessageSquare, path: '/sessions' },
    { label: 'Chats', icon: MessageCircle, path: '/chats' },
    { label: 'Digests', icon: Newspaper, path: '/digests' },
    { label: 'Costs', icon: BarChart3, path: '/costs' },
    { label: 'Keeper', icon: BrainCircuit, path: '/keeper' },
    { label: 'Logs', icon: ScrollText, path: '/logs' },
    { label: 'Settings', icon: Settings, path: '/settings' },
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
            'w-6 h-6 rounded-none bg-bg-elevated border border-border-bright',
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
          <img src="/favicon.png" alt="ISLI" className="w-5 h-5 rounded-none shrink-0" />
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
                  'flex items-center gap-3 px-3 py-2 rounded-none transition-all duration-200 group',
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

      {/* Mobile Full-Page Nav Menu */}
      <AnimatePresence>
        {mobileOpen && (
          <MobileNavMenu
            agents={agents}
            cost={cost}
            navItems={navItems}
            currentPath={location.pathname}
            onClose={onCloseMobile ?? (() => {})}
          />
        )}
      </AnimatePresence>
    </>
  )
}

/* ────────────────────────────────────────────────────────────────────────── */

interface NavItemDef {
  label: string
  icon: React.ComponentType<{ className?: string }>
  path: string
}

function MobileNavMenu({
  agents,
  cost,
  navItems,
  currentPath,
  onClose,
}: {
  agents: Agent[]
  cost: CostDashboard | null
  navItems: NavItemDef[]
  currentPath: string
  onClose: () => void
}) {
  const navigate = useNavigate()
  const [page, setPage] = useState(0)
  const [dragPage, setDragPage] = useState<number | null>(null)
  const activePage = dragPage ?? page

  const containerRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)

  const segmentedRef = useRef<HTMLDivElement>(null)
  const [segmentedWidth, setSegmentedWidth] = useState(0)
  const segmentWidth = segmentedWidth > 0 ? segmentedWidth / 2 : 0

  const pillX = useMotionValue(0)
  const contentX = useMotionValue(0)

  // Fast spring for snap animation
  const fastSpring = { type: 'spring' as const, damping: 22, stiffness: 450, mass: 0.8 }

  // Measure swipe container
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const observer = new ResizeObserver(() => setWidth(el.offsetWidth))
    observer.observe(el)
    setWidth(el.offsetWidth)
    return () => observer.disconnect()
  }, [])

  // Measure segmented control
  useEffect(() => {
    const el = segmentedRef.current
    if (!el) return
    const observer = new ResizeObserver(() => setSegmentedWidth(el.offsetWidth))
    observer.observe(el)
    setSegmentedWidth(el.offsetWidth)
    return () => observer.disconnect()
  }, [])

  // Animate pill to settled page
  useEffect(() => {
    if (!segmentWidth) return
    const target = page * segmentWidth
    const controls = animate(pillX, target, fastSpring)
    return () => controls.stop()
  }, [page, segmentWidth, pillX])

  // Animate content to settled page
  useEffect(() => {
    if (!width) return
    const target = page === 0 ? 0 : -width
    const controls = animate(contentX, target, fastSpring)
    return () => controls.stop()
  }, [page, width, contentX])

  const goTo = useCallback(
    (path: string) => {
      navigate(path)
      onClose()
    },
    [navigate, onClose]
  )

  const handleDrag = (_e: unknown, info: PanInfo) => {
    if (!width || !segmentWidth) return
    const rawProgress = page + -info.offset.x / width
    const p = Math.max(0, Math.min(1, rawProgress))
    // Direct real-time sync — zero lag between drag, content, and pill
    contentX.set(-p * width)
    pillX.set(p * segmentWidth)
    const mid = p < 0.5 ? 0 : 1
    setDragPage((prev) => (prev !== mid ? mid : prev))
  }

  const handleDragEnd = (_e: unknown, info: PanInfo) => {
    setDragPage(null)
    const threshold = width * 0.15 // 15% drag threshold (faster snap)
    const velocityThreshold = 250 // lower velocity threshold
    if (info.offset.x < -threshold && page === 0) {
      setPage(1)
    } else if (info.offset.x > threshold && page === 1) {
      setPage(0)
    } else if (info.velocity.x < -velocityThreshold && page === 0) {
      setPage(1)
    } else if (info.velocity.x > velocityThreshold && page === 1) {
      setPage(0)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.18, ease: 'easeOut' }}
      className="fixed inset-0 z-50 md:hidden bg-bg-base flex flex-col"
      style={{ paddingTop: 'env(safe-area-inset-top)', paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      {/* ── Top Bar ── */}
      <div className="shrink-0 flex items-center justify-between px-5 pt-5 pb-2">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-2xl bg-bg-elevated border border-border-dim flex items-center justify-center overflow-hidden shadow-sm">
            <img src="/favicon.png" alt="ISLI" className="w-5 h-5" />
          </div>
          <span className="text-base font-display font-bold tracking-wider text-text-primary">
            ISLI<span className="text-accent-cyan">.</span>BOARD
          </span>
        </div>
        <motion.button
          whileTap={{ scale: 0.88 }}
          onClick={onClose}
          className="w-10 h-10 rounded-full bg-bg-elevated/80 border border-border-dim flex items-center justify-center text-text-secondary hover:text-text-primary hover:border-border-bright active:bg-bg-elevated transition-colors"
          aria-label="Close menu"
        >
          <X className="w-5 h-5" />
        </motion.button>
      </div>

      {/* ── Segmented Control (synced with swipe) ── */}
      <div className="shrink-0 px-5 pb-3">
        <div
          ref={segmentedRef}
          className="relative flex p-[3px] rounded-xl bg-bg-elevated/50 border border-border-dim/40 backdrop-blur-md"
        >
          {/* Sliding pill */}
          {segmentWidth > 0 && (
            <motion.div
              className="absolute top-[3px] bottom-[3px] rounded-[10px] bg-accent-cyan shadow-glow-cyan"
              style={{ width: '50%', x: pillX }}
            />
          )}

          <button
            onClick={() => setPage(0)}
            className={cn(
              'relative z-10 flex-1 py-[7px] text-[11px] font-display font-bold uppercase tracking-widest rounded-[10px] transition-colors duration-150',
              activePage === 0 ? 'text-white' : 'text-text-muted hover:text-text-secondary'
            )}
          >
            Navigation
          </button>
          <button
            onClick={() => setPage(1)}
            className={cn(
              'relative z-10 flex-1 py-[7px] text-[11px] font-display font-bold uppercase tracking-widest rounded-[10px] transition-colors duration-150',
              activePage === 1 ? 'text-white' : 'text-text-muted hover:text-text-secondary'
            )}
          >
            Agents
          </button>
        </div>
      </div>

      {/* ── Swipeable Content ── */}
      <div ref={containerRef} className="flex-1 overflow-hidden relative">
        <motion.div
          className="flex h-full will-change-transform"
          style={{ x: contentX, touchAction: 'pan-y', overscrollBehaviorX: 'contain' }}
          drag="x"
          dragConstraints={{ left: -width, right: 0 }}
          dragElastic={0.18}
          onDrag={handleDrag}
          onDragEnd={handleDragEnd}
        >
          {/* ── Interface 1: Navigation Grid ── */}
          <div className="w-full h-full shrink-0 overflow-y-auto custom-scrollbar px-5 pb-6" style={{ touchAction: 'pan-y' }}>
            <div className="grid grid-cols-3 gap-[10px]">
              {navItems.map((item) => {
                const isActive = currentPath === item.path
                return (
                  <motion.button
                    key={item.path}
                    whileTap={{ scale: 0.94 }}
                    onClick={() => goTo(item.path)}
                    className={cn(
                      'flex flex-col items-center gap-2 p-2.5 rounded-2xl transition-colors duration-150',
                      'bg-bg-surface/40 border backdrop-blur-sm',
                      isActive
                        ? 'border-accent-cyan/30 bg-accent-cyan/[0.07] shadow-[0_0_12px_-2px_var(--glow-cyan)]'
                        : 'border-border-dim/40 hover:bg-bg-elevated/50 hover:border-border-dim/70'
                    )}
                  >
                    <div
                      className={cn(
                        'w-12 h-12 rounded-[14px] flex items-center justify-center transition-all duration-200',
                        isActive
                          ? 'bg-accent-cyan/15 text-accent-cyan shadow-inner'
                          : 'bg-bg-elevated/60 text-text-primary'
                      )}
                    >
                      <item.icon
                        className={cn(
                          'w-6 h-6 transition-colors',
                          isActive ? 'text-accent-cyan' : 'text-text-secondary'
                        )}
                      />
                    </div>
                    <span
                      className={cn(
                        'text-[10px] font-semibold text-center leading-tight tracking-wide',
                        isActive ? 'text-accent-cyan font-bold' : 'text-text-secondary'
                      )}
                    >
                      {item.label}
                    </span>
                  </motion.button>
                )
              })}
            </div>
          </div>

          {/* ── Interface 2: Agents Grid ── */}
          <div className="w-full h-full shrink-0 overflow-y-auto custom-scrollbar px-5 pb-6" style={{ touchAction: 'pan-y' }}>
            {/* Cost summary strip */}
            {cost && (
              <div className="flex items-center gap-2 mb-4 p-3 rounded-2xl bg-bg-surface/40 border border-border-dim/40 backdrop-blur-sm">
                <div className="flex-1 flex flex-col items-center gap-0.5">
                  <span className="text-base font-mono-data font-bold text-accent-cyan leading-none">{agents.length}</span>
                  <span className="text-[9px] font-mono uppercase tracking-wider text-text-muted">Agents</span>
                </div>
                <div className="w-px h-8 bg-border-dim/50" />
                <div className="flex-1 flex flex-col items-center gap-0.5">
                  <span className="text-base font-mono-data font-bold text-accent-amber leading-none">{cost.total_tasks}</span>
                  <span className="text-[9px] font-mono uppercase tracking-wider text-text-muted">Tasks</span>
                </div>
                <div className="w-px h-8 bg-border-dim/50" />
                <div className="flex-1 flex flex-col items-center gap-0.5">
                  <span className="text-base font-mono-data font-bold text-accent-green leading-none">${cost.total_cost_usd.toFixed(1)}</span>
                  <span className="text-[9px] font-mono uppercase tracking-wider text-text-muted">Cost</span>
                </div>
              </div>
            )}

            <div className="flex flex-col gap-2.5">
              {agents.map((agent) => {
                const pct = agent.token_budget
                  ? Math.min((agent.token_used / agent.token_budget) * 100, 100)
                  : 0
                const tokenColor =
                  agent.token_budget && agent.token_used / agent.token_budget > 0.8
                    ? 'bg-accent-red'
                    : agent.token_budget && agent.token_used / agent.token_budget > 0.5
                    ? 'bg-accent-amber'
                    : 'bg-accent-cyan'
                return (
                  <motion.button
                    key={agent.id}
                    whileTap={{ scale: 0.97 }}
                    onClick={() => goTo(`/agents/${agent.id}`)}
                    className={cn(
                      'flex items-center gap-3 p-3 rounded-2xl text-left transition-colors duration-150',
                      'bg-bg-surface/40 border border-border-dim/40 backdrop-blur-sm',
                      'hover:bg-bg-elevated/50 hover:border-border-dim/70'
                    )}
                  >
                    {/* Avatar with status */}
                    <div className="relative shrink-0">
                      <div
                        className={cn(
                          'w-11 h-11 rounded-xl flex items-center justify-center border',
                          agent.status === 'online'
                            ? 'bg-accent-green/10 border-accent-green/20 text-accent-green'
                            : agent.status === 'paused'
                            ? 'bg-accent-amber/10 border-accent-amber/20 text-accent-amber'
                            : 'bg-accent-red/10 border-accent-red/20 text-accent-red'
                        )}
                      >
                        <Cpu className="w-5 h-5" />
                      </div>
                      <span
                        className={cn(
                          'absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-bg-base',
                          agent.status === 'online' && 'bg-accent-green',
                          agent.status === 'paused' && 'bg-accent-amber',
                          agent.status === 'offline' && 'bg-accent-red',
                          agent.status === 'registered' && 'bg-accent-cyan',
                          agent.status === 'deleted' && 'bg-text-muted'
                        )}
                      />
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2 mb-0.5">
                        <h3 className="text-sm font-display font-bold text-text-primary truncate">
                          {agent.name}
                        </h3>
                        <StatusBadge status={agent.status} />
                      </div>

                      <div className="flex items-center gap-1.5 mb-2">
                        <span className="text-[10px] px-1.5 py-[1px] rounded-md bg-bg-elevated border border-border-dim/50 text-text-muted font-mono-data truncate max-w-[90px]">
                          {agent.model_id || 'Not set'}
                        </span>
                        <span className="text-[10px] px-1.5 py-[1px] rounded-md bg-bg-elevated border border-border-dim/50 text-text-muted font-mono-data">
                          {agent.skills.length} tools
                        </span>
                      </div>

                      {/* Token bar */}
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-[3px] rounded-full bg-border-dim/40 overflow-hidden">
                          <div
                            className={cn('h-full rounded-full transition-all duration-500', tokenColor)}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span className="text-[9px] font-mono-data text-text-muted shrink-0 leading-none">
                          {agent.token_used.toLocaleString()}
                        </span>
                      </div>
                    </div>
                  </motion.button>
                )
              })}
            </div>

            {agents.length === 0 && (
              <div className="flex flex-col items-center justify-center py-16">
                <div className="w-16 h-16 rounded-2xl bg-bg-elevated/50 border border-border-dim/40 flex items-center justify-center mb-4">
                  <Bot className="w-8 h-8 text-text-muted/30" />
                </div>
                <h3 className="text-base font-display font-bold text-text-secondary">No Agents Found</h3>
                <p className="text-xs text-text-muted mt-1 text-center max-w-[220px]">
                  Create your first agent to get started.
                </p>
              </div>
            )}
          </div>
        </motion.div>
      </div>

      {/* ── Bottom Indicator (pill + dots) ── */}
      <div className="shrink-0 flex flex-col items-center gap-2 pb-5 pt-1">
        <div className="flex items-center gap-2">
          <motion.div
            animate={{
              width: activePage === 0 ? 20 : 6,
              backgroundColor: activePage === 0 ? 'var(--accent-cyan)' : 'var(--border-dim)',
            }}
            transition={fastSpring}
            className="h-1.5 rounded-full"
          />
          <motion.div
            animate={{
              width: activePage === 1 ? 20 : 6,
              backgroundColor: activePage === 1 ? 'var(--accent-cyan)' : 'var(--border-dim)',
            }}
            transition={fastSpring}
            className="h-1.5 rounded-full"
          />
        </div>
        <span className="text-[9px] text-text-muted/50 font-mono-data uppercase tracking-widest">
          Swipe to switch
        </span>
      </div>
    </motion.div>
  )
}

/* ────────────────────────────────────────────────────────────────────────── */

function CollapsedSidebar({ agents, cost }: { agents: Agent[]; cost: CostDashboard | null }) {
  return (
    <div className="flex-1 flex flex-col items-center pt-8 pb-4 gap-6 min-h-0 overflow-y-auto">
      {/* Agent count */}
      <div className="flex flex-col items-center gap-1.5 group cursor-default">
        <div className="relative">
          <div className="w-8 h-8 rounded-none bg-bg-elevated border border-border-dim flex items-center justify-center text-accent-cyan">
            <span className="text-xs font-mono-data font-bold">{agents.length}</span>
          </div>
          {agents.some((a) => a.status === 'online') && (
            <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-none bg-accent-green border-2 border-bg-surface" />
          )}
        </div>
      </div>

      {/* Task count */}
      <div className="flex flex-col items-center gap-1.5">
        <div className="w-8 h-8 rounded-none bg-bg-elevated border border-border-dim flex items-center justify-center text-accent-amber">
          <span className="text-xs font-mono-data font-bold">{cost?.total_tasks ?? 0}</span>
        </div>
      </div>

      {/* Spend */}
      <div className="flex flex-col items-center gap-1.5">
        <div className="w-8 h-8 rounded-none bg-bg-elevated border border-border-dim flex items-center justify-center text-accent-green">
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
          <div key={a.id} className="group relative flex items-center justify-center w-full">
            <div
              className={cn(
                'w-2.5 h-2.5 rounded-none transition-all',
                a.status === 'online'
                  ? 'bg-accent-green shadow-[0_0_6px_rgba(0,255,136,0.5)]'
                  : a.status === 'paused'
                  ? 'bg-accent-amber'
                  : 'bg-accent-red'
              )}
              title={a.name}
            />
            {/* Tooltip on hover */}
            <div className="absolute left-full ml-2 px-2 py-1 rounded-none bg-bg-elevated border border-border-dim text-[10px] text-text-secondary font-mono-data whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
              {a.name}
            </div>
          </div>
        ))}
        {agents.length > 8 && (
          <span className="text-[8px] font-mono-data text-text-muted">+{agents.length - 8}</span>
        )}
      </div>
    </div>
  )
}
