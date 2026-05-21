import { useState, useEffect, useCallback, useMemo } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useAgents, useUpdateAgent, useDeleteAgent } from '@/hooks/useAgents'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { StatusBadge } from './StatusBadge'
import { 
  Bot, 
  Cpu, 
  ChevronLeft, 
  Save, 
  Radio, 
  Wrench, 
  FileJson, 
  AlertCircle,
  Plus,
  X,
  Zap,
  ShieldAlert,
  Calendar,
  Terminal
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Agent } from '@/types'

const PROVIDERS = ['ollama', 'anthropic', 'openai', 'kimi', 'deepseek', 'google', 'azure']
const CHANNEL_OPTIONS = ['telegram', 'whatsapp', 'email', 'web']

function buildForm(agent: Agent | null): Record<string, unknown> {
  if (!agent) return {}
  return {
    name: agent.name,
    description: agent.description ?? '',
    persona: agent.persona ?? '',
    model_provider: agent.model_provider ?? '',
    model_id: agent.model_id ?? '',
    token_budget: agent.token_budget ?? '',
    max_retries: agent.max_retries,
    fallback_agent_id: agent.fallback_agent_id ?? '',
    channels: [...agent.channels],
    skills: [...agent.skills],
    config: JSON.stringify(agent.config ?? {}, null, 2),
  }
}

function extractPayload(form: Record<string, unknown>): Partial<Agent> {
  const payload: Partial<Agent> = {}

  const name = String(form.name || '').trim()
  if (name) payload.name = name

  const description = String(form.description || '').trim()
  if (description) payload.description = description

  const persona = String(form.persona || '').trim()
  if (persona) payload.persona = persona

  const model_provider = String(form.model_provider || '').trim()
  if (model_provider) payload.model_provider = model_provider

  const model_id = String(form.model_id || '').trim()
  if (model_id) payload.model_id = model_id

  const tokenBudget = Number(form.token_budget)
  if (!Number.isNaN(tokenBudget) && tokenBudget > 0) {
    payload.token_budget = tokenBudget
  } else {
    payload.token_budget = null
  }

  const maxRetries = Number(form.max_retries)
  if (!Number.isNaN(maxRetries)) payload.max_retries = maxRetries

  const fallback = String(form.fallback_agent_id || '').trim()
  payload.fallback_agent_id = fallback || null

  payload.channels = Array.isArray(form.channels) ? form.channels : []
  payload.skills = Array.isArray(form.skills) ? form.skills : []

  try {
    payload.config = JSON.parse(String(form.config || '{}'))
  } catch {
    payload.config = {}
  }

  return payload
}

export function AgentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: agents = [], isLoading: agentsLoading } = useAgents()
  const updateAgent = useUpdateAgent()
  const deleteAgent = useDeleteAgent()

  const agent = useMemo(() => agents.find((a) => a.id === id), [agents, id])

  const [form, setForm] = useState<Record<string, unknown>>({})
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [skillInput, setSkillInput] = useState('')
  const [hasChanges, setHasChanges] = useState(false)

  useEffect(() => {
    if (agent) {
      setForm(buildForm(agent))
      setHasChanges(false)
    }
  }, [agent])

  const setField = useCallback((key: string, value: unknown) => {
    setForm((prev: Record<string, unknown>) => ({ ...prev, [key]: value }))
    setHasChanges(true)
  }, [])

  const toggleChannel = useCallback((ch: string) => {
    setForm((prev: Record<string, unknown>) => {
      const current = (prev.channels as string[]) || []
      const next = current.includes(ch)
        ? current.filter((c) => c !== ch)
        : [...current, ch]
      return { ...prev, channels: next }
    })
    setHasChanges(true)
  }, [])

  const addSkill = useCallback(() => {
    const raw = skillInput.trim()
    if (!raw) return
    setForm((prev: Record<string, unknown>) => {
      const current = (prev.skills as string[]) || []
      if (current.includes(raw)) return prev
      return { ...prev, skills: [...current, raw] }
    })
    setSkillInput('')
    setHasChanges(true)
  }, [skillInput])

  const removeSkill = useCallback((skill: string) => {
    setForm((prev: Record<string, unknown>) => {
      const current = (prev.skills as string[]) || []
      return { ...prev, skills: current.filter((s) => s !== skill) }
    })
    setHasChanges(true)
  }, [])

  const handleJsonBlur = useCallback(() => {
    try {
      JSON.parse(String(form.config || '{}'))
      setJsonError(null)
    } catch (e) {
      setJsonError(e instanceof Error ? e.message : 'Invalid JSON')
    }
  }, [form.config])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!agent) return
    try {
      JSON.parse(String(form.config || '{}'))
    } catch {
      setJsonError('Please fix JSON errors before saving')
      return
    }
    const payload = extractPayload(form)
    updateAgent.mutate(
      { id: agent.id, payload },
      {
        onSuccess: () => {
          setHasChanges(false)
        },
      }
    )
  }

  const handleDelete = async () => {
    if (!agent) return
    if (!confirm(`Are you sure you want to delete ${agent.name}? This action cannot be undone.`)) return

    deleteAgent.mutate(agent.id, {
      onSuccess: () => {
        navigate('/agents')
      },
    })
  }

  if (agentsLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-base">
        <div className="w-8 h-8 border-2 border-accent-cyan/20 border-t-accent-cyan rounded-full animate-spin" />
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

  const channels = (form.channels as string[]) || []
  const skills = (form.skills as string[]) || []

  return (
    <div className="flex-1 overflow-y-auto bg-bg-base">
      <form onSubmit={handleSubmit} className="p-6 md:p-8 max-w-7xl mx-auto space-y-8">
        {/* Navigation & Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="flex flex-col gap-4">
            <Link 
              to="/agents"
              className="flex items-center gap-2 text-xs font-display font-bold uppercase tracking-widest text-text-muted hover:text-accent-cyan transition-colors w-fit"
            >
              <ChevronLeft className="w-4 h-4" />
              Back to Agents
            </Link>
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 rounded-2xl bg-bg-surface border border-border-dim flex items-center justify-center text-accent-cyan shadow-sm">
                <Cpu className="w-8 h-8" />
              </div>
              <div>
                <h1 className="text-2xl font-display font-bold text-text-primary">{agent.name}</h1>
                <div className="flex items-center gap-3 mt-1">
                   <StatusBadge status={agent.status} />
                   <span className="text-[10px] font-mono-data text-text-muted uppercase tracking-wider">ID: {agent.id}</span>
                </div>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
             <Button 
               type="button" 
               variant="secondary" 
               onClick={() => navigate(`/agents/${id}/logs`)}
             >
               <Terminal className="w-4 h-4 mr-2" />
               Live Logs
             </Button>
             <Button 
               type="button" 
               variant="ghost" 
               onClick={() => setForm(buildForm(agent))}
               disabled={!hasChanges || updateAgent.isPending}
             >
               Discard
             </Button>
             <Button 
               type="submit" 
               className={cn(hasChanges ? "shadow-glow-cyan" : "opacity-50")}
               disabled={!hasChanges || updateAgent.isPending || !!jsonError}
             >
               <Save className="w-4 h-4 mr-2" />
               {updateAgent.isPending ? 'Saving...' : 'Save Changes'}
             </Button>
          </div>
        </div>

        {/* Dashboard Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column: General & Capabilities */}
          <div className="lg:col-span-2 space-y-6">
            {/* Overview Card */}
            <div className="bg-bg-surface border border-border-dim rounded-2xl overflow-hidden shadow-sm">
              <div className="px-6 py-4 border-b border-border-dim bg-bg-elevated/30 flex items-center gap-2">
                <Bot className="w-4 h-4 text-accent-cyan" />
                <h2 className="text-xs font-display font-bold uppercase tracking-widest text-text-secondary">Agent Overview</h2>
              </div>
              <div className="p-6 space-y-6">
                <div className="space-y-2">
                  <label className="text-xs font-display uppercase tracking-wider text-text-muted font-bold">Display Name</label>
                  <Input
                    value={String(form.name || '')}
                    onChange={(e) => setField('name', e.target.value)}
                    placeholder="Enter agent name"
                    className="bg-bg-base/50"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-display uppercase tracking-wider text-text-muted font-bold">Description</label>
                  <textarea
                    value={String(form.description || '')}
                    onChange={(e) => setField('description', e.target.value)}
                    placeholder="What is the primary purpose of this agent?"
                    rows={3}
                    className="w-full bg-bg-base/50 border border-border-dim rounded-xl px-4 py-3 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-cyan transition-all resize-none font-sans"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-display uppercase tracking-wider text-text-muted font-bold">Persona</label>
                  <textarea
                    value={String(form.persona || '')}
                    onChange={(e) => setField('persona', e.target.value)}
                    placeholder="Define the agent's personality, tone, and specific instructions..."
                    rows={6}
                    className="w-full bg-bg-base/50 border border-border-dim rounded-xl px-4 py-3 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-cyan transition-all resize-none font-sans"
                  />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t border-border-dim/50">
                  <div className="flex items-center gap-3">
                    <Calendar className="w-4 h-4 text-text-muted" />
                    <div>
                      <div className="text-[10px] text-text-muted uppercase tracking-wider">Created</div>
                      <div className="text-xs font-mono-data">{new Date(agent.created_at).toLocaleString()}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <Calendar className="w-4 h-4 text-text-muted" />
                    <div>
                      <div className="text-[10px] text-text-muted uppercase tracking-wider">Last Updated</div>
                      <div className="text-xs font-mono-data">{new Date(agent.updated_at).toLocaleString()}</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Capabilities Card */}
            <div className="bg-bg-surface border border-border-dim rounded-2xl overflow-hidden shadow-sm">
               <div className="px-6 py-4 border-b border-border-dim bg-bg-elevated/30 flex items-center gap-2">
                <Wrench className="w-4 h-4 text-accent-cyan" />
                <h2 className="text-xs font-display font-bold uppercase tracking-widest text-text-secondary">Capabilities & Skills</h2>
              </div>
              <div className="p-6 space-y-8">
                {/* Channels */}
                <div className="space-y-4">
                  <label className="text-xs font-display uppercase tracking-wider text-text-muted font-bold flex items-center gap-2">
                    <Radio className="w-3.5 h-3.5" />
                    Communication Channels
                  </label>
                  <div className="flex flex-wrap gap-3">
                    {CHANNEL_OPTIONS.map((ch) => (
                      <button
                        key={ch}
                        type="button"
                        onClick={() => toggleChannel(ch)}
                        className={cn(
                          "px-4 py-2 rounded-xl text-xs font-display font-bold uppercase tracking-wide border transition-all flex items-center gap-2",
                          channels.includes(ch)
                            ? "bg-accent-cyan/10 border-accent-cyan text-accent-cyan shadow-glow-cyan/10"
                            : "bg-bg-base/50 border-border-dim text-text-muted hover:border-border-bright hover:text-text-primary"
                        )}
                      >
                        <div className={cn("w-1.5 h-1.5 rounded-full", channels.includes(ch) ? "bg-accent-cyan" : "bg-text-muted")} />
                        {ch}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Skills */}
                <div className="space-y-4">
                  <label className="text-xs font-display uppercase tracking-wider text-text-muted font-bold flex items-center gap-2">
                    <Zap className="w-3.5 h-3.5" />
                    Specialized Skills (Tools)
                  </label>
                  <div className="flex gap-2">
                    <Input
                      value={skillInput}
                      onChange={(e) => setSkillInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault()
                          addSkill()
                        }
                      }}
                      placeholder="e.g. web-search, db-query"
                      className="flex-1 bg-bg-base/50"
                    />
                    <Button type="button" variant="secondary" onClick={addSkill}>
                      <Plus className="w-4 h-4 mr-2" />
                      Add
                    </Button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {skills.length === 0 && (
                      <p className="text-xs text-text-muted italic py-2">No skills assigned yet.</p>
                    )}
                    {skills.map((skill) => (
                      <div
                        key={skill}
                        className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-bg-elevated border border-border-dim text-text-primary text-xs font-mono-data"
                      >
                        {skill}
                        <button
                          type="button"
                          onClick={() => removeSkill(skill)}
                          className="text-text-muted hover:text-accent-red transition-colors"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Right Column: Model Config & Advanced */}
          <div className="space-y-6">
            {/* Model Card */}
            <div className="bg-bg-surface border border-border-dim rounded-2xl overflow-hidden shadow-sm">
              <div className="px-6 py-4 border-b border-border-dim bg-bg-elevated/30 flex items-center gap-2">
                <Zap className="w-4 h-4 text-accent-amber" />
                <h2 className="text-xs font-display font-bold uppercase tracking-widest text-text-secondary">Model Strategy</h2>
              </div>
              <div className="p-6 space-y-5">
                <div className="space-y-2">
                  <label className="text-xs font-display uppercase tracking-wider text-text-muted font-bold">Provider</label>
                  <Select
                    value={String(form.model_provider || '')}
                    onChange={(e) => setField('model_provider', e.target.value)}
                    className="bg-bg-base/50"
                  >
                    <option value="">Select provider</option>
                    {PROVIDERS.map((p) => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </Select>
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-display uppercase tracking-wider text-text-muted font-bold">Model ID</label>
                  <Input
                    value={String(form.model_id || '')}
                    onChange={(e) => setField('model_id', e.target.value)}
                    placeholder="e.g. gpt-4o"
                    className="bg-bg-base/50"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-display uppercase tracking-wider text-text-muted font-bold">Fallback Agent ID</label>
                  <Input
                    value={String(form.fallback_agent_id || '')}
                    onChange={(e) => setField('fallback_agent_id', e.target.value)}
                    placeholder="Agent ID to use as backup"
                    className="bg-bg-base/50"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="text-xs font-display uppercase tracking-wider text-text-muted font-bold">Token Budget</label>
                    <Input
                      type="number"
                      value={String(form.token_budget ?? '')}
                      onChange={(e) => setField('token_budget', e.target.value === '' ? '' : Number(e.target.value))}
                      placeholder="Infinite"
                      className="bg-bg-base/50"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-xs font-display uppercase tracking-wider text-text-muted font-bold">Max Retries</label>
                    <Input
                      type="number"
                      value={String(form.max_retries ?? 3)}
                      onChange={(e) => setField('max_retries', Number(e.target.value))}
                      className="bg-bg-base/50"
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Advanced Config Card */}
            <div className="bg-bg-surface border border-border-dim rounded-2xl overflow-hidden shadow-sm">
              <div className="px-6 py-4 border-b border-border-dim bg-bg-elevated/30 flex items-center gap-2">
                <FileJson className="w-4 h-4 text-accent-cyan" />
                <h2 className="text-xs font-display font-bold uppercase tracking-widest text-text-secondary">Advanced Config</h2>
              </div>
              <div className="p-6 space-y-4">
                <div className="space-y-2">
                  <label className="text-xs font-display uppercase tracking-wider text-text-muted font-bold flex justify-between items-center">
                    JSON Payload
                    {jsonError && <span className="text-accent-red font-mono-data lowercase tracking-normal flex items-center gap-1"><AlertCircle className="w-3 h-3" /> invalid</span>}
                  </label>
                  <textarea
                    value={String(form.config || '{}')}
                    onChange={(e) => setField('config', e.target.value)}
                    onBlur={handleJsonBlur}
                    rows={12}
                    className={cn(
                      "w-full bg-bg-base/50 border rounded-xl px-4 py-3 text-[11px] font-mono-data text-text-primary placeholder:text-text-muted focus:outline-none transition-all resize-none",
                      jsonError ? "border-accent-red" : "border-border-dim focus:border-accent-cyan"
                    )}
                  />
                  <p className="text-[10px] text-text-muted">Directly modify the agent's internal configuration state.</p>
                </div>
              </div>
            </div>

            {/* Danger Zone */}
            <div className="bg-accent-red/5 border border-accent-red/20 rounded-2xl p-6">
               <h3 className="text-xs font-display font-bold uppercase tracking-widest text-accent-red flex items-center gap-2 mb-4">
                 <ShieldAlert className="w-4 h-4" />
                 Danger Zone
               </h3>
               <p className="text-xs text-text-muted mb-4">Deleting this agent is permanent and will stop all active tasks assigned to it.</p>
               <Button 
                type="button"
                variant="ghost" 
                onClick={handleDelete}
                disabled={deleteAgent.isPending}
                className="w-full border-accent-red/20 text-accent-red hover:bg-accent-red/10 hover:text-accent-red"
               >
                 {deleteAgent.isPending ? 'Deleting...' : 'Delete Agent'}
               </Button>
            </div>
          </div>
        </div>
      </form>
    </div>
  )
}
