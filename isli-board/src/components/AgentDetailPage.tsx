import { useState, useEffect, useCallback, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useAgents, useUpdateAgent, useDeleteAgent } from '@/hooks/useAgents'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { Label } from '@/components/ui/Label'
import { ConfirmationModal } from '@/components/ui/ConfirmationModal'
import { getJSON, postJSON, postFormData } from '@/lib/api'
import {
  Bot,
  ChevronLeft,
  Wrench,
  FileJson,
  Zap,
  ShieldAlert,
  Terminal,
  Brain,
  Eye,
  EyeOff,
  Play,
  Square,
  RotateCcw,
  KeyRound,
  Hammer,
  Users,
  Radio,
  X,
  Camera,
} from 'lucide-react'

import { cn } from '@/lib/utils'
import type { Agent, ProviderSettings } from '@/types'

function buildForm(agent: Agent | null): Record<string, unknown> {
  if (!agent) return {}
  const config = agent.config ?? {}
  return {
    name: agent.name,
    description: agent.description ?? '',
    persona: agent.persona ?? '',
    model_provider: agent.model_provider ?? '',
    model_id: agent.model_id ?? '',
    token_budget: agent.token_budget ?? '',
    turn_token_cap: agent.turn_token_cap ?? '',
    max_retries: agent.max_retries,
    fallback_agent_id: agent.fallback_agent_id ?? '',
    known_agent_ids: [...agent.known_agent_ids],
    channels: [...agent.channels],
    config: JSON.stringify(config, null, 2),
    api_key: '',
    has_api_key: agent.has_api_key,
    api_key_mask: agent.api_key_mask,
    model_routing_enabled: agent.model_routing_enabled || false,
    secondary_models: agent.secondary_models || [],
    streaming_mode: agent.config?.streaming_mode || 'silent',
    stream_chunk_size: agent.config?.stream_chunk_size ?? 5,
    stream_delay_ms: agent.config?.stream_delay_ms ?? 20,
    pii_mesh_enabled: agent.config?.pii_mesh_enabled || false,
    pii_use_slm: agent.config?.pii_use_slm || false,
  }
}

export function AgentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: agents = [], isLoading: agentsLoading } = useAgents()
  const updateAgent = useUpdateAgent()
  const deleteAgent = useDeleteAgent()
  const queryClient = useQueryClient()

  const { data: providers = [] } = useQuery({
    queryKey: ['providers'],
    queryFn: () => getJSON<ProviderSettings[]>('/v1/settings/providers'),
    staleTime: 30000,
  })

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
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [savingSection, setSavingSection] = useState<string | null>(null)
  const [showApiKey, setShowApiKey] = useState(false)
  const [restarting, setRestarting] = useState(false)
  const [addingSecondaryModel, setAddingSecondaryModel] = useState(false)
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
  const [newSecondaryModel, setNewSecondaryModel] = useState({
    provider: '',
    model_id: '',
    label: '',
    description: '',
    cost_tier: 'standard',
  })

  useEffect(() => {
    if (agent) {
      setForm(buildForm(agent))
      setJsonError(null)
    }
  }, [agent])

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

  const addSecondaryModel = useCallback(() => {
    if (!newSecondaryModel.provider || !newSecondaryModel.model_id) return
    setForm((prev: Record<string, unknown>) => {
      const current = (prev.secondary_models as Agent['secondary_models']) || []
      return {
        ...prev,
        secondary_models: [...current, { ...newSecondaryModel }],
      }
    })
    setNewSecondaryModel({ provider: '', model_id: '', label: '', description: '', cost_tier: 'standard' })
    setAddingSecondaryModel(false)
  }, [newSecondaryModel])

  const removeSecondaryModel = useCallback((index: number) => {
    setForm((prev: Record<string, unknown>) => {
      const current = [...((prev.secondary_models as Agent['secondary_models']) || [])]
      current.splice(index, 1)
      return { ...prev, secondary_models: current }
    })
  }, [])

  const handleJsonBlur = useCallback(() => {
    try {
      JSON.parse(String(form.config || '{}'))
      setJsonError(null)
    } catch (e) {
      setJsonError(e instanceof Error ? e.message : 'Invalid JSON')
    }
  }, [form.config])

  // ── Per-section dirty detection ────────────────────────────────────────────

  const overviewDirty = useMemo(() => {
    if (!agent) return false
    return (
      form.name !== agent.name ||
      (form.description || '') !== (agent.description || '') ||
      (form.persona || '') !== (agent.persona || '')
    )
  }, [form, agent])

  const modelDirty = useMemo(() => {
    if (!agent) return false
    const agentConfig = agent.config || {}
    return (
      (form.model_provider || '') !== (agent.model_provider || '') ||
      (form.model_id || '') !== (agent.model_id || '') ||
      (form.fallback_agent_id || '') !== (agent.fallback_agent_id || '') ||
      (form.token_budget || '') !== (agent.token_budget || '') ||
      (form.turn_token_cap || '') !== (agent.turn_token_cap || '') ||
      Number(form.max_retries ?? 3) !== Number(agent.max_retries ?? 3) ||
      String(form.api_key || '').trim() !== '' ||
      Boolean(form.model_routing_enabled) !== Boolean(agent.model_routing_enabled) ||
      JSON.stringify(form.secondary_models || []) !== JSON.stringify(agent.secondary_models || []) ||
      String(form.streaming_mode || 'silent') !== String(agentConfig.streaming_mode || 'silent') ||
      Boolean(form.pii_mesh_enabled) !== Boolean(agentConfig.pii_mesh_enabled) ||
      Boolean(form.pii_use_slm) !== Boolean(agentConfig.pii_use_slm)
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

  const advancedDirty = useMemo(() => {
    if (!agent) return false
    try {
      const current = JSON.stringify(
        JSON.parse(String(form.config || '{}')),
        null,
        2
      )
      const original = JSON.stringify(agent.config || {}, null, 2)
      return current !== original
    } catch {
      return true
    }
  }, [form, agent])

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

  const saveModel = () => {
    if (!agent) return
    const payload: Partial<Agent> = {}
    const model_provider = String(form.model_provider || '').trim()
    if (model_provider) payload.model_provider = model_provider
    const model_id = String(form.model_id || '').trim()
    if (model_id) payload.model_id = model_id
    const fallback = String(form.fallback_agent_id || '').trim()
    payload.fallback_agent_id = fallback || null
    const tokenBudget = Number(form.token_budget)
    if (!Number.isNaN(tokenBudget) && tokenBudget > 0) payload.token_budget = tokenBudget
    else payload.token_budget = null
    const turnTokenCap = Number(form.turn_token_cap)
    if (!Number.isNaN(turnTokenCap) && turnTokenCap > 0) payload.turn_token_cap = turnTokenCap
    else payload.turn_token_cap = null
    const maxRetries = Number(form.max_retries)
    if (!Number.isNaN(maxRetries)) payload.max_retries = maxRetries
    const apiKey = String(form.api_key || '').trim()
    if (apiKey) payload.api_key = apiKey

    payload.model_routing_enabled = Boolean(form.model_routing_enabled)
    payload.secondary_models = Array.isArray(form.secondary_models) ? form.secondary_models : []

    // Include streaming_mode and PII mesh in config blob
    const config = JSON.parse(String(form.config || '{}'))
    config.streaming_mode = String(form.streaming_mode || 'silent')
    config.pii_mesh_enabled = Boolean(form.pii_mesh_enabled)
    config.pii_use_slm = Boolean(form.pii_use_slm)
    payload.config = config

    setSavingSection('model')
    updateAgent.mutate(
      { id: agent.id, payload },
      { onSettled: () => setSavingSection(null) }
    )
  }

  const saveAdvanced = () => {
    if (!agent) return
    try {
      const config = JSON.parse(String(form.config || '{}'))
      setJsonError(null)
      setSavingSection('advanced')
      updateAgent.mutate(
        { id: agent.id, payload: { config } },
        { onSettled: () => setSavingSection(null) }
      )
    } catch (e) {
      setJsonError(e instanceof Error ? e.message : 'Invalid JSON')
    }
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
    const payload: Partial<Agent> = {
      known_agent_ids: Array.isArray(form.known_agent_ids) ? form.known_agent_ids : [],
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

  const resetModel = () => {
    if (!agent) return
    setForm((prev) => ({
      ...prev,
      model_provider: agent.model_provider ?? '',
      model_id: agent.model_id ?? '',
      fallback_agent_id: agent.fallback_agent_id ?? '',
      token_budget: agent.token_budget ?? '',
      turn_token_cap: agent.turn_token_cap ?? '',
      max_retries: agent.max_retries,
      api_key: '',
      model_routing_enabled: agent.model_routing_enabled || false,
      secondary_models: agent.secondary_models || [],
      pii_mesh_enabled: agent.config?.pii_mesh_enabled || false,
      pii_use_slm: agent.config?.pii_use_slm || false,
    }))
  }

  const resetAdvanced = () => {
    if (!agent) return
    setForm((prev) => ({
      ...prev,
      config: JSON.stringify(agent.config || {}, null, 2),
    }))
    setJsonError(null)
  }

  const performDelete = async () => {
    if (!agent) return
    deleteAgent.mutate(agent.id, {
      onSuccess: () => {
        navigate('/agents')
      },
    })
  }

  const handleClearApiKey = () => {
    if (!agent) return
    setConfirmModal({
      open: true,
      title: 'Clear API Key Override',
      description: 'Are you sure you want to clear the custom API key? This node will revert to using global provider credentials.',
      onConfirm: async () => {
        setField('api_key', '')
        updateAgent.mutate(
          { id: agent.id, payload: { api_key: null } },
          { onSettled: () => queryClient.invalidateQueries({ queryKey: ['agents'] }) }
        )
      },
      variant: 'warning',
      confirmText: 'Clear Key',
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

                <div className="p-8 border border-border-bright bg-bg-surface space-y-8">
                  {/* Avatar Upload */}
                  <div className="flex flex-col items-center gap-4 pb-8 border-b border-border-dim">
                    <div className="relative group">
                      <div className="w-32 h-32 bg-bg-elevated border-2 border-border-dim overflow-hidden flex items-center justify-center relative">
                        {agent.picture ? (
                          <img 
                            src={`/api/v1/blobs/${agent.picture}`} 
                            alt={agent.name} 
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <Bot className="w-12 h-12 text-text-muted opacity-20" />
                        )}
                        
                        <label className="absolute inset-0 bg-black/60 flex flex-col items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer">
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
                    <p className="text-[9px] text-text-muted uppercase tracking-[0.2em]">NODE_IDENTICON_v1.0</p>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-[10px] tracking-widest text-text-muted uppercase">Display Name</Label>
                    <Input
                      value={String(form.name || '')}
                      onChange={(e) => setField('name', e.target.value)}
                      placeholder="Enter agent name"
                      className="bg-bg-surface border-border-bright focus:border-accent-cyan text-text-primary rounded-none h-12"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-[10px] tracking-widest text-text-muted uppercase">Description</Label>
                    <Textarea
                      value={String(form.description || '')}
                      onChange={(e) => setField('description', e.target.value)}
                      placeholder="What is the primary purpose of this agent?"
                      rows={3}
                      className="bg-bg-surface border-border-bright focus:border-accent-cyan text-text-primary rounded-none resize-none p-4"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-[10px] tracking-widest text-text-muted uppercase">Behavioral Persona</Label>
                    <Textarea
                      value={String(form.persona || '')}
                      onChange={(e) => setField('persona', e.target.value)}
                      placeholder="Define the agent's personality, tone, and specific instructions..."
                      rows={8}
                      className="bg-bg-surface border-border-bright focus:border-accent-cyan text-text-primary rounded-none resize-none p-4 leading-relaxed"
                    />
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-8 pt-8 border-t border-border-dim">
                    <div className="flex flex-col gap-1">
                      <span className="text-[9px] text-text-muted uppercase tracking-widest">Initialization Date</span>
                      <span className="text-xs text-text-secondary tabular-nums">{new Date(agent.created_at).toLocaleString()}</span>
                    </div>
                    <div className="flex flex-col gap-1">
                      <span className="text-[9px] text-text-muted uppercase tracking-widest">Last Synced</span>
                      <span className="text-xs text-text-secondary tabular-nums">{new Date(agent.updated_at).toLocaleString()}</span>
                    </div>
                  </div>

                  {overviewDirty && (
                    <div className="pt-6 border-t border-border-dim flex justify-end gap-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={resetOverview}
                        disabled={savingSection === 'overview'}
                        className="text-text-muted hover:text-text-primary rounded-none px-6"
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

            {/* Right Column: Model, Skills, Advanced, Danger */}
            <div className="space-y-12">
              {/* Model Card */}
              <div className="space-y-6">
                <div className="space-y-1">
                  <h2 className="text-sm font-bold tracking-[0.2em] text-text-secondary uppercase flex items-center gap-3">
                    <Zap className="w-4 h-4" />
                    02 // MODEL_STRATEGY
                  </h2>
                  <div className="h-px bg-border-dim w-full" />
                </div>

                <div className="p-8 border border-border-bright bg-bg-surface space-y-6">
                  <div className="space-y-2">
                    <Label className="text-[10px] tracking-widest text-text-muted uppercase">Primary Provider</Label>
                    <Select
                      value={String(form.model_provider || '')}
                      onChange={(e) => {
                        setField('model_provider', e.target.value)
                        setField('model_id', '')
                      }}
                      className="bg-bg-surface border-border-bright focus:border-accent-cyan text-text-primary rounded-none h-12"
                    >
                      <option value="">SELECT_PROVIDER</option>
                      {providers
                        .filter((p) => p.enabled)
                        .map((p) => (
                          <option key={p.provider} value={p.provider}>{p.provider.toUpperCase()}</option>
                        ))}
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-[10px] tracking-widest text-text-muted uppercase">Reasoning Engine</Label>
                    <Select
                      value={String(form.model_id || '')}
                      onChange={(e) => setField('model_id', e.target.value)}
                      disabled={!form.model_provider}
                      className="bg-bg-surface border-border-bright focus:border-accent-cyan text-text-primary rounded-none h-12 disabled:opacity-20"
                    >
                      <option value="">{form.model_provider ? 'SELECT_MODEL' : 'AWAITING_PROVIDER'}</option>
                      {providers
                        .find((p) => p.provider === form.model_provider)
                        ?.models.filter((m) => m.enabled)
                        .map((m) => (
                          <option key={m.model_id} value={m.model_id}>{m.name || m.model_id}</option>
                        ))}
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-[10px] tracking-widest text-text-muted uppercase">Streaming Interface</Label>
                    <Select
                      value={String(form.streaming_mode || 'silent')}
                      onChange={(e) => {
                        setField('streaming_mode', e.target.value)
                        const cfg = { ...(agent?.config || {}) }
                        cfg.streaming_mode = e.target.value
                        setField('config', JSON.stringify(cfg, null, 2))
                      }}
                      className="bg-bg-surface border-border-bright focus:border-accent-cyan text-text-primary rounded-none h-12"
                    >
                      <option value="silent">BATCH_MODE (SILENT)</option>
                      <option value="text">LIVE_TEXT (REVEAL)</option>
                      <option value="tools">LIVE_TOOLS (CARDS)</option>
                      <option value="trace">PROCESS_TRACE (FULL)</option>
                      <option value="debug">DEBUG_MODE (RAW)</option>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-[10px] tracking-widest text-text-muted uppercase flex justify-between">
                      API Key Override
                      {Boolean(form.has_api_key) && (
                        <button
                          type="button"
                          onClick={handleClearApiKey}
                          className="text-[9px] text-accent-red hover:text-accent-red/80 uppercase tracking-widest"
                        >
                          [ CLEAR ]
                        </button>
                      )}
                    </Label>
                    <div className="relative">
                      <Input
                        type={showApiKey ? 'text' : 'password'}
                        value={String(form.api_key || '')}
                        onChange={(e) => setField('api_key', e.target.value)}
                        placeholder={form.has_api_key ? 'REPLACE_EXISTING_KEY' : 'OPTIONAL_OVERRIDE'}
                        className="bg-bg-surface border-border-bright focus:border-accent-cyan text-text-primary rounded-none h-12 pr-12"
                      />
                      <button
                        type="button"
                        onClick={() => setShowApiKey((v) => !v)}
                        className="absolute right-4 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
                      >
                        {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                    {Boolean(form.has_api_key) && (
                      <span className="text-[9px] text-text-muted font-mono tabular-nums tracking-widest">
                        CURRENT_MASK: {String(form.api_key_mask || '')}
                      </span>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label className="text-[10px] tracking-widest text-text-muted uppercase">Lifetime Limit</Label>
                      <Input
                        type="number"
                        value={String(form.token_budget ?? '')}
                        onChange={(e) => setField('token_budget', e.target.value === '' ? '' : Number(e.target.value))}
                        placeholder="UNLIMITED"
                        className="bg-bg-surface border-border-bright focus:border-accent-cyan text-text-primary rounded-none h-12"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-[10px] tracking-widest text-text-muted uppercase">Per-Turn Cap</Label>
                      <Input
                        type="number"
                        value={String(form.turn_token_cap ?? '')}
                        onChange={(e) => setField('turn_token_cap', e.target.value === '' ? '' : Number(e.target.value))}
                        placeholder="e.g. 4000"
                        className="bg-bg-surface border-border-bright focus:border-accent-cyan text-text-primary rounded-none h-12"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label className="text-[10px] tracking-widest text-text-muted uppercase">Retry Limit</Label>
                      <Input
                        type="number"
                        value={String(form.max_retries ?? 3)}
                        onChange={(e) => setField('max_retries', Number(e.target.value))}
                        className="bg-bg-surface border-border-bright focus:border-accent-cyan text-text-primary rounded-none h-12"
                      />
                    </div>
                  </div>

                  {/* Model Routing */}
                  <div className="pt-6 border-t border-border-dim space-y-4">
                    <div className="flex items-center justify-between">
                      <Label className="text-[10px] tracking-widest text-text-muted uppercase flex items-center gap-2">
                        <Brain className="w-3.5 h-3.5 text-accent-cyan" />
                        Model Routing
                      </Label>
                      <button
                        type="button"
                        onClick={() => setField('model_routing_enabled', !form.model_routing_enabled)}
                        className={cn(
                          "relative inline-flex h-5 w-9 items-center rounded-none transition-colors border",
                          form.model_routing_enabled ? "border-accent-cyan bg-accent-cyan/10" : "border-border-bright bg-bg-elevated"
                        )}
                      >
                        <span
                          className={cn(
                            "inline-block h-3 w-3 transform rounded-none transition-transform",
                            form.model_routing_enabled ? "translate-x-5 bg-accent-cyan" : "translate-x-1 bg-text-muted"
                          )}
                        />
                      </button>
                    </div>
                    <p className="text-[10px] text-text-secondary leading-relaxed uppercase tracking-tight">
                      When enabled, the Keeper local model analyzes each task and selects the optimal engine from the registry below.
                    </p>

                    {Boolean(form.model_routing_enabled) && (
                      <div className="space-y-4 animate-in fade-in slide-in-from-top-2 duration-300">
                        {((form.secondary_models || []) as Agent['secondary_models']).map((m, i) => (
                          <div
                            key={i}
                            className="flex items-center justify-between bg-bg-surface border border-border-dim p-4"
                          >
                            <div className="flex flex-col gap-1">
                              <div className="flex items-center gap-3">
                                <span className="text-[10px] font-bold text-text-primary tabular-nums">
                                  {m.provider.toUpperCase()} // {m.model_id.toUpperCase()}
                                </span>
                                <span className={cn(
                                  "text-[8px] font-bold px-1.5 py-0.5 border uppercase tracking-widest",
                                  m.cost_tier === 'local' ? "border-accent-green/30 text-accent-green" :
                                  m.cost_tier === 'premium' ? "border-accent-violet/30 text-accent-violet" : "border-border-bright text-text-muted"
                                )}>
                                  {m.cost_tier}
                                </span>
                              </div>
                              {m.label && <span className="text-[9px] text-text-muted uppercase">{m.label}</span>}
                            </div>
                            <button
                              type="button"
                              onClick={() => removeSecondaryModel(i)}
                              className="text-text-muted hover:text-accent-red transition-colors"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ))}

                        {addingSecondaryModel ? (
                          <div className="border border-border-bright bg-bg-surface p-6 space-y-4">
                            <div className="grid grid-cols-2 gap-4">
                              <div className="space-y-1.5">
                                <Label className="text-[10px] tracking-widest text-text-muted uppercase">Provider</Label>
                                <Select
                                  value={newSecondaryModel.provider}
                                  onChange={(e) => setNewSecondaryModel((prev) => ({ ...prev, provider: e.target.value, model_id: '' }))}
                                  className="bg-bg-surface border-border-bright text-[11px] h-10 rounded-none"
                                >
                                  <option value="">SELECT</option>
                                  {providers.filter(p => p.enabled).map(p => (
                                    <option key={p.provider} value={p.provider}>{p.provider.toUpperCase()}</option>
                                  ))}
                                </Select>
                              </div>
                              <div className="space-y-1.5">
                                <Label className="text-[10px] tracking-widest text-text-muted uppercase">Model</Label>
                                <Select
                                  value={newSecondaryModel.model_id}
                                  onChange={(e) => setNewSecondaryModel((prev) => ({ ...prev, model_id: e.target.value }))}
                                  disabled={!newSecondaryModel.provider}
                                  className="bg-bg-surface border-border-bright text-[11px] h-10 rounded-none disabled:opacity-20"
                                >
                                  <option value="">SELECT</option>
                                  {providers.find(p => p.provider === newSecondaryModel.provider)?.models.filter(m => m.enabled).map(m => (
                                    <option key={m.model_id} value={m.model_id}>{m.model_id.toUpperCase()}</option>
                                  ))}
                                </Select>
                              </div>
                            </div>
                            <div className="flex justify-end gap-3 pt-2">
                               <button
                                onClick={() => setAddingSecondaryModel(false)}
                                className="text-[10px] text-text-muted hover:text-text-primary uppercase tracking-widest"
                               >
                                CANCEL
                               </button>
                               <button
                                onClick={addSecondaryModel}
                                disabled={!newSecondaryModel.provider || !newSecondaryModel.model_id}
                                className="text-[10px] text-accent-cyan hover:text-text-primary uppercase tracking-widest font-bold"
                               >
                                REGISTER_NODE
                               </button>
                            </div>
                          </div>
                        ) : (
                          <button
                            type="button"
                            onClick={() => setAddingSecondaryModel(true)}
                            className="w-full py-3 border border-dashed border-border-bright text-[10px] text-text-muted hover:text-accent-cyan hover:border-accent-cyan transition-all uppercase tracking-widest"
                          >
                            + ADD_SECONDARY_NODE
                          </button>
                        )}
                      </div>
                    )}
                  </div>

                  {/* PII Mesh */}
                  <div className="pt-6 border-t border-border-dim space-y-4">
                    <div className="flex items-center justify-between">
                      <Label className="text-[10px] tracking-widest text-text-muted uppercase flex items-center gap-2">
                        <ShieldAlert className="w-3.5 h-3.5 text-accent-amber" />
                        PII Mesh
                      </Label>
                      <button
                        type="button"
                        onClick={() => {
                          const enabled = !form.pii_mesh_enabled
                          setField('pii_mesh_enabled', enabled)
                          if (!enabled) setField('pii_use_slm', false)
                        }}
                        className={cn(
                          "relative inline-flex h-5 w-9 items-center rounded-none transition-colors border",
                          form.pii_mesh_enabled ? "border-accent-amber bg-accent-amber/10" : "border-border-bright bg-bg-elevated"
                        )}
                      >
                        <span
                          className={cn(
                            "inline-block h-3 w-3 transform rounded-none transition-transform",
                            form.pii_mesh_enabled ? "translate-x-5 bg-accent-amber" : "translate-x-1 bg-text-muted"
                          )}
                        />
                      </button>
                    </div>
                    <p className="text-[10px] text-text-secondary leading-relaxed uppercase tracking-tight">
                      When enabled, the Keeper local model anonymizes PII before sending messages to the cloud LLM. Re-hydration happens locally in the agent runner.
                    </p>

                    {Boolean(form.pii_mesh_enabled) && (
                      <div className="flex items-center justify-between animate-in fade-in slide-in-from-top-2 duration-300">
                        <Label className="text-[10px] tracking-widest text-text-muted uppercase flex items-center gap-2">
                          <Brain className="w-3 h-3 text-accent-cyan" />
                          Use Keeper SLM for PII detection
                        </Label>
                        <button
                          type="button"
                          onClick={() => setField('pii_use_slm', !form.pii_use_slm)}
                          className={cn(
                            "relative inline-flex h-5 w-9 items-center rounded-none transition-colors border",
                            form.pii_use_slm ? "border-accent-cyan bg-accent-cyan/10" : "border-border-bright bg-bg-elevated"
                          )}
                        >
                          <span
                            className={cn(
                              "inline-block h-3 w-3 transform rounded-none transition-transform",
                              form.pii_use_slm ? "translate-x-5 bg-accent-cyan" : "translate-x-1 bg-text-muted"
                            )}
                          />
                        </button>
                      </div>
                    )}
                  </div>

                  {modelDirty && (
                    <div className="pt-6 border-t border-border-dim flex justify-end gap-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={resetModel}
                        disabled={savingSection === 'model'}
                        className="text-text-muted hover:text-text-primary rounded-none px-6"
                      >
                        DISCARD
                      </Button>
                      <Button
                        type="button"
                        onClick={saveModel}
                        disabled={savingSection === 'model'}
                        className="bg-accent-cyan text-black hover:opacity-90 rounded-none px-8 font-bold text-xs tracking-widest"
                      >
                        {savingSection === 'model' ? 'SYNCING...' : 'COMMIT_CHANGES'}
                      </Button>
                    </div>
                  )}
                </div>
              </div>

              {/* Advanced Config Card */}
              <div className="space-y-6">
                <div className="space-y-1">
                  <h2 className="text-sm font-bold tracking-[0.2em] text-text-secondary uppercase flex items-center gap-3">
                    <FileJson className="w-4 h-4" />
                    03 // RAW_CONFIGURATION
                  </h2>
                  <div className="h-px bg-border-dim w-full" />
                </div>

                <div className="p-8 border border-border-bright bg-bg-surface space-y-6">
                  <div className="space-y-2">
                    <Label className="text-[10px] tracking-widest text-text-muted uppercase flex justify-between">
                      Internal State (JSON)
                      {jsonError && <span className="text-accent-red font-bold">PARSING_ERROR</span>}
                    </Label>
                    <Textarea
                      value={String(form.config || '{}')}
                      onChange={(e) => setField('config', e.target.value)}
                      onBlur={handleJsonBlur}
                      rows={10}
                      className={cn(
                        "bg-bg-surface border-border-bright focus:border-accent-cyan text-text-secondary rounded-none resize-none font-mono text-[11px] leading-relaxed p-4",
                        jsonError && "border-accent-red focus:border-accent-red"
                      )}
                    />
                  </div>

                  {advancedDirty && (
                    <div className="pt-6 border-t border-border-dim flex justify-end gap-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={resetAdvanced}
                        disabled={savingSection === 'advanced' || !!jsonError}
                        className="text-text-muted hover:text-text-primary rounded-none px-6"
                      >
                        DISCARD
                      </Button>
                      <Button
                        type="button"
                        onClick={saveAdvanced}
                        disabled={savingSection === 'advanced' || !!jsonError}
                        className="bg-accent-cyan text-black hover:opacity-90 rounded-none px-8 font-bold text-xs tracking-widest"
                      >
                        {savingSection === 'advanced' ? 'SYNCING...' : 'COMMIT_CHANGES'}
                      </Button>
                    </div>
                  )}
                </div>
              </div>

              {/* Known Agents / Delegation Card */}
              <div className="space-y-6">
                <div className="space-y-1">
                  <h2 className="text-sm font-bold tracking-[0.2em] text-text-secondary uppercase flex items-center gap-3">
                    <Users className="w-4 h-4" />
                    04 // DELEGATION_MAP
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
