import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useAgents, useUpdateAgent, useDeleteAgent } from '@/hooks/useAgents'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Label } from '@/components/ui/Label'
import { ConfirmationModal } from '@/components/ui/ConfirmationModal'
import { postJSON, postFormData } from '@/lib/api'
import {
  Bot,
  ChevronLeft,
  Wrench,
  FileJson,
  Zap,
  ShieldAlert,
  Terminal,
  Brain,
  BookOpen,
  Play,
  Square,
  RotateCcw,
  KeyRound,
  Hammer,
  Users,
  Radio,
  Camera,
} from 'lucide-react'

import { cn } from '@/lib/utils'
import type { Agent } from '@/types'

function buildForm(agent: Agent | null, allAgents: Agent[]): Record<string, unknown> {
  if (!agent) return {}
  const validPeerIds = new Set(allAgents.filter(a => !a.deleted_at).map(a => a.id))
  const known_agent_ids: string[] = (agent.known_agent_ids || []).filter(id => validPeerIds.has(id))
  return {
    name: agent.name,
    description: agent.description ?? '',
    persona: agent.persona ?? '',
    known_agent_ids,
    channels: [...agent.channels],
  }
}

export function AgentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: agents = [], isLoading: agentsLoading } = useAgents()
  const updateAgent = useUpdateAgent()
  const deleteAgent = useDeleteAgent()
  const queryClient = useQueryClient()

  const agent = useMemo(() => agents.find((a) => a.id === id), [agents, id])
  const [uploadingPicture, setUploadingPicture] = useState(false)

  const handleUploadPicture = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !agent) return

    setUploadingPicture(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      await postFormData(`/v1/agents/${agent.id}/picture`, formData)
      queryClient.invalidateQueries({ queryKey: ['agents'] })
    } catch (err) {
      console.error('Failed to upload picture:', err)
    } finally {
      setUploadingPicture(false)
    }
  }

  // Auto-refresh while starting, registered, or rebuilding
  useEffect(() => {
    if (agent?.status === 'starting' || agent?.status === 'registered' || agent?.status === 'rebuilding') {
      const timer = setInterval(() => {
        queryClient.invalidateQueries({ queryKey: ['agents'] })
      }, 3000)
      return () => clearInterval(timer)
    }
  }, [agent?.status, queryClient])

  const handleStart = async () => {
    if (!id) return
    try {
      await postJSON(`/v1/agents/${id}/start`, {})
      queryClient.invalidateQueries({ queryKey: ['agents'] })
    } catch (err) {
      console.error('Failed to start agent:', err)
    }
  }

  const performStop = async () => {
    if (!id) return
    try {
      await postJSON(`/v1/agents/${id}/stop`, {})
      queryClient.invalidateQueries({ queryKey: ['agents'] })
    } catch (err) {
      console.error('Failed to stop agent:', err)
    }
  }

  const handleStop = () => {
    setConfirmModal({
      open: true,
      title: 'Stop Node',
      description: 'Are you sure you want to stop this agent? Active tasks may be interrupted.',
      onConfirm: performStop,
      variant: 'warning',
      confirmText: 'Stop Node',
    })
  }

  const performRestart = async () => {
    if (!id) return
    setRestarting(true)
    try {
      await postJSON(`/v1/agents/${id}/restart`, {})
      queryClient.invalidateQueries({ queryKey: ['agents'] })
    } catch (err) {
      console.error('Failed to restart agent:', err)
    } finally {
      setRestarting(false)
    }
  }

  const handleRestart = () => {
    setConfirmModal({
      open: true,
      title: 'Restart Node',
      description: 'Restarting the node will refresh its internal state. The agent will be briefly offline.',
      onConfirm: performRestart,
      variant: 'primary',
      confirmText: 'Restart',
    })
  }

  const performRebuildAndRestart = async () => {
    if (!id) return
    setRestarting(true)
    try {
      await postJSON(`/v1/agents/${id}/restart?rebuild=true`, {})
      queryClient.invalidateQueries({ queryKey: ['agents'] })
    } catch (err) {
      console.error('Failed to rebuild and restart agent:', err)
    } finally {
      setRestarting(false)
    }
  }

  const handleRebuildAndRestart = () => {
    setConfirmModal({
      open: true,
      title: 'Rebuild & Restart',
      description: 'This will rebuild the agent image from source and restart the container. This process may take a minute.',
      onConfirm: performRebuildAndRestart,
      variant: 'primary',
      confirmText: 'Rebuild & Restart',
    })
  }

  const [form, setForm] = useState<Record<string, unknown>>({})
  const [savingSection, setSavingSection] = useState<string | null>(null)
  const [restarting, setRestarting] = useState(false)
  const [confirmModal, setConfirmModal] = useState<{
    open: boolean;
    title: string;
    description: string;
    onConfirm: () => void | Promise<void>;
    variant: 'primary' | 'danger' | 'warning';
    confirmText?: string;
  }>({
    open: false,
    title: '',
    description: '',
    onConfirm: () => {},
    variant: 'primary',
  })

  const overviewDirty = useMemo(() => {
    if (!agent) return false
    return (
      form.name !== agent.name ||
      (form.description || '') !== (agent.description || '') ||
      (form.persona || '') !== (agent.persona || '')
    )
  }, [form, agent])

  const peersDirty = useMemo(() => {
    if (!agent) return false
    const current = (form.known_agent_ids as string[]) || []
    const original = agent.known_agent_ids || []
    if (current.length !== original.length) return true
    const sortedCurrent = [...current].sort()
    const sortedOriginal = [...original].sort()
    return sortedCurrent.some((id, i) => id !== sortedOriginal[i])
  }, [form, agent])

  const isAnyDirty = useMemo(() => overviewDirty || peersDirty, [overviewDirty, peersDirty])
  const lastLoadedId = useRef<string | undefined>(undefined)

  useEffect(() => {
    if (agent && (id !== lastLoadedId.current || !isAnyDirty)) {
      setForm(buildForm(agent, agents))
      lastLoadedId.current = id
    }
  }, [agent, agents, id, isAnyDirty])

  const setField = useCallback((key: string, value: unknown) => {
    setForm((prev: Record<string, unknown>) => ({ ...prev, [key]: value }))
  }, [])

  const toggleKnownAgent = useCallback((peerId: string) => {
    setForm((prev: Record<string, unknown>) => {
      const current = (prev.known_agent_ids as string[]) || []
      const next = current.includes(peerId)
        ? current.filter((id) => id !== peerId)
        : [...current, peerId]
      return { ...prev, known_agent_ids: next }
    })
  }, [])

  // ── Per-section save handlers ──────────────────────────────────────────────

  const saveOverview = () => {
    if (!agent) return
    const payload: Partial<Agent> = {
      name: String(form.name || '').trim(),
      description: String(form.description || '').trim() || null,
      persona: String(form.persona || '').trim() || null,
    }
    setSavingSection('overview')
    updateAgent.mutate(
      { id: agent.id, payload },
      { onSettled: () => setSavingSection(null) }
    )
  }

  // ── Per-section reset handlers ─────────────────────────────────────────────

  const resetOverview = () => {
    if (!agent) return
    setForm((prev) => ({
      ...prev,
      name: agent.name,
      description: agent.description ?? '',
      persona: agent.persona ?? '',
    }))
  }

  const savePeers = () => {
    if (!agent) return
    const validPeerIds = new Set(agents.filter(a => !a.deleted_at).map(a => a.id))
    const payload: Partial<Agent> = {
      known_agent_ids: (Array.isArray(form.known_agent_ids) ? form.known_agent_ids : [])
        .filter((id: string) => validPeerIds.has(id)),
    }
    setSavingSection('peers')
    updateAgent.mutate(
      { id: agent.id, payload },
      { onSettled: () => setSavingSection(null) }
    )
  }

  const resetPeers = () => {
    if (!agent) return
    setForm((prev) => ({
      ...prev,
      known_agent_ids: [...(agent.known_agent_ids || [])],
    }))
  }

  const performDelete = async () => {
    if (!agent) return
    deleteAgent.mutate(agent.id, {
      onSuccess: () => {
        navigate('/agents')
      },
    })
  }

  const handleDelete = () => {
    if (!agent) return
    setConfirmModal({
      open: true,
      title: 'Decommission Node',
      description: `Are you sure you want to delete ${agent.name}? This action cannot be undone and will remove all associated configurations.`,
      onConfirm: performDelete,
      variant: 'danger',
      confirmText: 'Decommission',
    })
  }

  if (agentsLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-base">
        <div className="w-8 h-8 border-2 border-accent-cyan/20 border-t-accent-cyan rounded-none animate-spin" />
      </div>
    )
  }

  if (!agent) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-bg-base p-8">
        <ShieldAlert className="w-16 h-16 text-accent-red mb-4" />
        <h1 className="text-2xl font-display font-bold text-text-primary">Agent Not Found</h1>
        <p className="text-text-secondary mt-2 mb-8">The agent you are looking for does not exist or has been deleted.</p>
        <Button onClick={() => navigate('/agents')}>Back to Agents</Button>
      </div>
    )
  }

  return (
    <div className="flex-1 bg-bg-base flex flex-col font-mono overflow-hidden">
      {/* Top Header / Status Bar */}
      <div className="h-12 border-b border-border-dim flex items-center justify-between px-6 bg-bg-base shrink-0">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/agents')}
            className="text-text-secondary hover:text-text-primary transition-colors flex items-center gap-2 text-xs tracking-widest"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
            BACK
          </button>
          <div className="h-4 w-px bg-border-dim" />
          <h1 className="text-xs tracking-[0.3em] font-bold text-text-secondary">AGENT_CONFIG_v2.0</h1>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <div className={cn(
              "w-1.5 h-1.5 rounded-none animate-pulse",
              agent.status === 'online' ? "bg-accent-cyan" : "bg-text-muted"
            )} />
            <span className={cn(
              "text-[10px] tracking-widest uppercase",
              agent.status === 'online' ? "text-accent-cyan" : "text-text-muted"
            )}>
              {agent.status}
            </span>
          </div>
          <div className="h-4 w-px bg-border-dim" />
          <span className="text-[10px] text-text-muted tabular-nums uppercase">ID:{agent.id}</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 md:p-12 lg:p-16">
        <div className="max-w-6xl mx-auto space-y-12">
          {/* Action Grid Section */}
          <section className="space-y-6">
            <div className="space-y-1">
              <h2 className="text-sm font-bold tracking-[0.2em] text-text-secondary uppercase">00 // SYSTEM_CONTROLS</h2>
              <div className="h-px bg-border-dim w-full" />
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-border-dim border border-border-dim shadow-2xl">
              {/* Row 1: Lifecycle */}
              {(agent.status === 'stopped' || agent.status === 'registered' || agent.status === 'crashed' || agent.status === 'offline') ? (
                <button
                  onClick={handleStart}
                  className="bg-bg-base hover:bg-accent-cyan/5 p-6 flex flex-col gap-3 group transition-all"
                >
                  <Play className="w-5 h-5 text-text-muted group-hover:text-accent-cyan" />
                  <div className="flex flex-col text-left">
                    <span className="text-[10px] text-text-muted tracking-widest font-bold">LIFECYCLE</span>
                    <span className="text-sm font-bold text-text-primary group-hover:text-accent-cyan">START_NODE</span>
                  </div>
                </button>
              ) : (
                <button
                  onClick={handleStop}
                  className="bg-bg-base hover:bg-accent-red/5 p-6 flex flex-col gap-3 group transition-all"
                >
                  <Square className="w-5 h-5 text-accent-red/50 group-hover:text-accent-red" />
                  <div className="flex flex-col text-left">
                    <span className="text-[10px] text-text-muted tracking-widest font-bold">LIFECYCLE</span>
                    <span className="text-sm font-bold text-text-primary group-hover:text-accent-red">
                      {agent.status === 'starting' ? 'TERMINATING...' : 'STOP_NODE'}
                    </span>
                  </div>
                </button>
              )}

              <button
                onClick={handleRestart}
                disabled={restarting || agent.status === 'rebuilding'}
                className="bg-bg-base hover:bg-accent-amber/5 p-6 flex flex-col gap-3 group transition-all disabled:opacity-20"
              >
                <RotateCcw className="w-5 h-5 text-text-muted group-hover:text-accent-amber" />
                <div className="flex flex-col text-left">
                  <span className="text-[10px] text-text-muted tracking-widest font-bold">LIFECYCLE</span>
                  <span className="text-sm font-bold text-text-primary group-hover:text-accent-amber">RESTART_NODE</span>
                </div>
              </button>

              <button
                onClick={handleRebuildAndRestart}
                disabled={restarting || agent.status === 'rebuilding'}
                className="bg-bg-base hover:bg-accent-cyan/5 p-6 flex flex-col gap-3 group transition-all disabled:opacity-20"
              >
                <Hammer className="w-5 h-5 text-text-muted group-hover:text-accent-cyan" />
                <div className="flex flex-col text-left">
                  <span className="text-[10px] text-text-muted tracking-widest font-bold">LIFECYCLE</span>
                  <span className="text-sm font-bold text-text-primary group-hover:text-accent-cyan">REBUILD_IMAGE</span>
                </div>
              </button>

              <button
                onClick={() => navigate(`/agents/${id}/channels`)}
                className="bg-bg-base hover:bg-accent-cyan/5 p-6 flex flex-col gap-3 group transition-all"
              >
                <Radio className="w-5 h-5 text-text-muted group-hover:text-accent-cyan" />
                <div className="flex flex-col text-left">
                  <span className="text-[10px] text-text-muted tracking-widest font-bold">GATEWAY</span>
                  <span className="text-sm font-bold text-text-primary group-hover:text-accent-cyan">CHANNELS</span>
                </div>
              </button>

              {/* Row 2: Ops */}
              <button
                onClick={() => navigate(`/agents/${id}/logs`)}
                className="bg-bg-base hover:bg-accent-cyan/5 p-6 flex flex-col gap-3 group transition-all"
              >
                <Terminal className="w-5 h-5 text-text-muted group-hover:text-accent-cyan" />
                <div className="flex flex-col text-left">
                  <span className="text-[10px] text-text-muted tracking-widest font-bold">OBSERVABILITY</span>
                  <span className="text-sm font-bold text-text-primary group-hover:text-accent-cyan">LIVE_LOGS</span>
                </div>
              </button>

              <button
                onClick={() => navigate(`/agents/${id}/memory`)}
                className="bg-bg-base hover:bg-accent-cyan/5 p-6 flex flex-col gap-3 group transition-all"
              >
                <Brain className="w-5 h-5 text-text-muted group-hover:text-accent-cyan" />
                <div className="flex flex-col text-left">
                  <span className="text-[10px] text-text-muted tracking-widest font-bold">DATABASE</span>
                  <span className="text-sm font-bold text-text-primary group-hover:text-accent-cyan">MEMORY</span>
                </div>
              </button>

              <button
                onClick={() => navigate(`/agents/${id}/journals`)}
                className="bg-bg-base hover:bg-accent-cyan/5 p-6 flex flex-col gap-3 group transition-all"
              >
                <BookOpen className="w-5 h-5 text-text-muted group-hover:text-accent-cyan" />
                <div className="flex flex-col text-left">
                  <span className="text-[10px] text-text-muted tracking-widest font-bold">EPISODIC</span>
                  <span className="text-sm font-bold text-text-primary group-hover:text-accent-cyan">JOURNALS</span>
                </div>
              </button>

              <button
                onClick={() => navigate(`/agents/${id}/secrets`)}
                className="bg-bg-base hover:bg-accent-cyan/5 p-6 flex flex-col gap-3 group transition-all"
              >
                <KeyRound className="w-5 h-5 text-text-muted group-hover:text-accent-cyan" />
                <div className="flex flex-col text-left">
                  <span className="text-[10px] text-text-muted tracking-widest font-bold">SECURITY</span>
                  <span className="text-sm font-bold text-text-primary group-hover:text-accent-cyan">SECRETS</span>
                </div>
              </button>

              <button
                onClick={() => navigate(`/agents/${id}/skills`)}
                className="bg-bg-base hover:bg-accent-cyan/5 p-6 flex flex-col gap-3 group transition-all"
              >
                <Wrench className="w-5 h-5 text-text-muted group-hover:text-accent-cyan" />
                <div className="flex flex-col text-left">
                  <span className="text-[10px] text-text-muted tracking-widest font-bold">CAPABILITIES</span>
                  <span className="text-sm font-bold text-text-primary group-hover:text-accent-cyan">SKILLS</span>
                </div>
              </button>

              <button
                onClick={() => navigate(`/agents/${id}/model`)}
                className="bg-bg-base hover:bg-accent-cyan/5 p-6 flex flex-col gap-3 group transition-all"
              >
                <Zap className="w-5 h-5 text-text-muted group-hover:text-accent-cyan" />
                <div className="flex flex-col text-left">
                  <span className="text-[10px] text-text-muted tracking-widest font-bold">ENGINE</span>
                  <span className="text-sm font-bold text-text-primary group-hover:text-accent-cyan">MODEL_STRATEGY</span>
                </div>
              </button>

              <button
                onClick={() => navigate(`/agents/${id}/config`)}
                className="bg-bg-base hover:bg-accent-cyan/5 p-6 flex flex-col gap-3 group transition-all"
              >
                <FileJson className="w-5 h-5 text-text-muted group-hover:text-accent-cyan" />
                <div className="flex flex-col text-left">
                  <span className="text-[10px] text-text-muted tracking-widest font-bold">SYSTEM</span>
                  <span className="text-sm font-bold text-text-primary group-hover:text-accent-cyan">RAW_CONFIG</span>
                </div>
              </button>
            </div>
          </section>

          {/* Dashboard Content Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-12">
            {/* Left Column: General */}
            <div className="lg:col-span-2 space-y-12">
              {/* Overview Card */}
              <div className="space-y-6">
                <div className="space-y-1">
                  <h2 className="text-sm font-bold tracking-[0.2em] text-text-secondary uppercase flex items-center gap-3">
                    <Bot className="w-4 h-4" />
                    01 // NODE_OVERVIEW
                  </h2>
                  <div className="h-px bg-border-dim w-full" />
                </div>

                <div className="p-8 border border-border-bright bg-bg-surface">
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                    {/* Left Panel: Profile Info / Telemetry Badge */}
                    <div className="lg:col-span-1 flex flex-col items-center justify-between border-b lg:border-b-0 lg:border-r border-border-dim pb-8 lg:pb-0 lg:pr-8 gap-6">
                      <div className="w-full flex flex-col items-center text-center space-y-4">
                        <div className="relative group">
                          <div className="w-32 h-32 bg-bg-elevated border border-border-bright overflow-hidden flex items-center justify-center relative shadow-inner">
                            {agent.picture ? (
                              <img 
                                src={`/api/v1/blobs/${agent.picture}`} 
                                alt={agent.name} 
                                className="w-full h-full object-cover"
                              />
                            ) : (
                              <Bot className="w-12 h-12 text-text-muted opacity-25" />
                            )}
                            
                            <label className="absolute inset-0 bg-black/70 flex flex-col items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer">
                              <Camera className="w-6 h-6 text-white mb-2" />
                              <span className="text-[10px] text-white font-bold uppercase tracking-widest">
                                {uploadingPicture ? 'UPLOADING...' : 'CHANGE_IMAGE'}
                              </span>
                              <input 
                                type="file" 
                                className="hidden" 
                                accept="image/*" 
                                onChange={handleUploadPicture}
                                disabled={uploadingPicture}
                              />
                            </label>
                          </div>
                          
                          {uploadingPicture && (
                            <div className="absolute inset-0 flex items-center justify-center bg-bg-surface/50">
                              <div className="w-6 h-6 border-2 border-accent-cyan/20 border-t-accent-cyan rounded-full animate-spin" />
                            </div>
                          )}
                        </div>
                        
                        <div className="space-y-1">
                          <div className="text-sm font-bold text-text-primary uppercase tracking-wider">{agent.name}</div>
                          <div className="text-[9px] text-text-muted uppercase tracking-[0.2em]">NODE_IDENTICON_v1.0</div>
                        </div>
                      </div>

                      {/* Read-only system metrics / telemetry */}
                      <div className="w-full space-y-4 pt-6 border-t border-border-dim/50">
                        <div className="flex flex-col gap-1">
                          <span className="text-[9px] text-text-muted uppercase tracking-widest font-bold">Node Address (ID)</span>
                          <span className="text-[11px] text-text-secondary font-mono truncate select-all">{agent.id}</span>
                        </div>
                        <div className="flex flex-col gap-1">
                          <span className="text-[9px] text-text-muted uppercase tracking-widest font-bold">Initialization Date</span>
                          <span className="text-[11px] text-text-secondary tabular-nums font-mono">{new Date(agent.created_at).toLocaleString()}</span>
                        </div>
                        <div className="flex flex-col gap-1">
                          <span className="text-[9px] text-text-muted uppercase tracking-widest font-bold">Last Synced</span>
                          <span className="text-[11px] text-text-secondary tabular-nums font-mono">{new Date(agent.updated_at).toLocaleString()}</span>
                        </div>
                      </div>
                    </div>

                    {/* Right Panel: Fields Form */}
                    <div className="lg:col-span-2 space-y-6 flex flex-col justify-between h-full">
                      <div className="space-y-6">
                        <div className="space-y-2">
                          <Label className="text-[10px] tracking-widest text-text-muted uppercase font-bold">Display Name</Label>
                          <Input
                            value={String(form.name || '')}
                            onChange={(e) => setField('name', e.target.value)}
                            placeholder="Enter agent name"
                            className="bg-bg-base border-border-bright focus:border-accent-cyan text-text-primary rounded-none h-12 focus:ring-0 focus:outline-none transition-all"
                          />
                        </div>
                        <div className="space-y-2">
                          <Label className="text-[10px] tracking-widest text-text-muted uppercase font-bold">Description</Label>
                          <Textarea
                            value={String(form.description || '')}
                            onChange={(e) => setField('description', e.target.value)}
                            placeholder="What is the primary purpose of this agent?"
                            rows={3}
                            className="bg-bg-base border-border-bright focus:border-accent-cyan text-text-primary rounded-none resize-none p-4 focus:ring-0 focus:outline-none transition-all"
                          />
                        </div>
                        <div className="space-y-2">
                          <Label className="text-[10px] tracking-widest text-text-muted uppercase font-bold">Behavioral Persona</Label>
                          <Textarea
                            value={String(form.persona || '')}
                            onChange={(e) => setField('persona', e.target.value)}
                            placeholder="Define the agent's personality, tone, and specific instructions..."
                            rows={8}
                            className="bg-bg-base border-border-bright focus:border-accent-cyan text-text-primary rounded-none resize-none p-4 leading-relaxed focus:ring-0 focus:outline-none transition-all"
                          />
                        </div>
                      </div>

                      {overviewDirty && (
                        <div className="pt-6 border-t border-border-dim flex justify-end gap-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
                          <Button
                            type="button"
                            variant="ghost"
                            onClick={resetOverview}
                            disabled={savingSection === 'overview'}
                            className="text-text-muted hover:text-text-primary rounded-none px-6 font-bold text-xs tracking-widest"
                          >
                            DISCARD
                          </Button>
                          <Button
                            type="button"
                            onClick={saveOverview}
                            disabled={savingSection === 'overview'}
                            className="bg-accent-cyan text-black hover:opacity-90 rounded-none px-8 font-bold text-xs tracking-widest"
                          >
                            {savingSection === 'overview' ? 'SYNCING...' : 'COMMIT_CHANGES'}
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Right Column: Advanced, Danger */}
            <div className="space-y-12">
              {/* Known Agents / Delegation Card */}
              <div className="space-y-6">
                <div className="space-y-1">
                  <h2 className="text-sm font-bold tracking-[0.2em] text-text-secondary uppercase flex items-center gap-3">
                    <Users className="w-4 h-4" />
                    02 // DELEGATION_MAP
                  </h2>
                  <div className="h-px bg-border-dim w-full" />
                </div>

                <div className="p-8 border border-border-bright bg-bg-surface space-y-6">
                  <p className="text-[10px] text-text-secondary leading-relaxed uppercase tracking-tight">
                    Define the peer network for task orchestration. Selected nodes are eligible for task delegation via the global board.
                  </p>

                  <div className="flex flex-wrap gap-4">
                    {agents.filter(a => a.id !== id).map(peer => {
                      const selected = ((form.known_agent_ids as string[]) || []).includes(peer.id)
                      return (
                        <button
                          key={peer.id}
                          type="button"
                          onClick={() => toggleKnownAgent(peer.id)}
                          className={cn(
                            "px-4 py-2 border text-[10px] font-bold tracking-widest transition-all flex items-center gap-3",
                            selected
                              ? "border-accent-cyan bg-accent-cyan/10 text-text-primary"
                              : "border-border-bright bg-bg-elevated text-text-muted hover:border-border-bright"
                          )}
                        >
                          <div className={cn(
                            "w-1.5 h-1.5",
                            peer.status === 'online' ? "bg-accent-cyan" : "bg-text-muted"
                          )} />
                          {peer.name.toUpperCase()}
                        </button>
                      )
                    })}
                  </div>

                  {agents.filter(a => a.id !== id).length === 0 && (
                    <div className="py-8 border border-dashed border-border-dim flex justify-center italic">
                       <span className="text-[10px] text-text-muted uppercase tracking-widest text-center px-6">No eligible peer nodes found in registry</span>
                    </div>
                  )}

                  {peersDirty && (
                    <div className="pt-6 border-t border-border-dim flex justify-end gap-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={resetPeers}
                        disabled={savingSection === 'peers'}
                        className="text-text-muted hover:text-text-primary rounded-none px-6"
                      >
                        DISCARD
                      </Button>
                      <Button
                        type="button"
                        onClick={savePeers}
                        disabled={savingSection === 'peers'}
                        className="bg-accent-cyan text-black hover:opacity-90 rounded-none px-8 font-bold text-xs tracking-widest"
                      >
                        {savingSection === 'peers' ? 'SYNCING...' : 'COMMIT_CHANGES'}
                      </Button>
                    </div>
                  )}
                </div>
              </div>

              {/* Danger Zone */}
              <div className="p-8 border border-accent-red/30 bg-accent-red/5 space-y-6">
                <div className="flex items-center gap-3">
                  <ShieldAlert className="w-5 h-5 text-accent-red" />
                  <div className="flex flex-col">
                    <span className="text-[10px] font-bold tracking-[0.2em] text-accent-red uppercase">DESTRUCTIVE_ACTIONS</span>
                    <span className="text-[11px] text-text-muted">Permanently terminate the autonomous unit and its tasks.</span>
                  </div>
                </div>
                <Button
                  type="button"
                  onClick={handleDelete}
                  disabled={deleteAgent.isPending}
                  className="w-full bg-accent-red/5 border border-accent-red/30 text-accent-red hover:bg-accent-red hover:text-bg-base transition-all rounded-none h-12 font-bold text-xs tracking-widest"
                >
                  {deleteAgent.isPending ? 'TERMINATING...' : 'DECOMMISSION_NODE'}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
      <ConfirmationModal
        open={confirmModal.open}
        title={confirmModal.title}
        description={confirmModal.description}
        variant={confirmModal.variant}
        confirmText={confirmModal.confirmText}
        onConfirm={confirmModal.onConfirm}
        onClose={() => setConfirmModal(prev => ({ ...prev, open: false }))}
        isLoading={deleteAgent.isPending || restarting || updateAgent.isPending}
      />
    </div>
  )
}
