import { useState, useEffect, useCallback, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAgents, useUpdateAgent } from '@/hooks/useAgents'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Label } from '@/components/ui/Label'
import { getJSON } from '@/lib/api'
import {
  ChevronLeft,
  Zap,
  ShieldAlert,
  Brain,
  Eye,
  EyeOff,
  X,
} from 'lucide-react'

import { cn } from '@/lib/utils'
import type { Agent, ProviderSettings } from '@/types'

export function AgentModelPage() {
  const { id } = useParams<{ id: string }>()
  const { data: agents = [], isLoading: agentsLoading } = useAgents()
  const updateAgent = useUpdateAgent()

  const { data: providers = [] } = useQuery({
    queryKey: ['providers'],
    queryFn: () => getJSON<ProviderSettings[]>('/v1/settings/providers'),
    staleTime: 30000,
  })

  const agent = useMemo(() => agents.find((a) => a.id === id), [agents, id])

  const [form, setForm] = useState<Record<string, any>>({})
  const [synced, setSynced] = useState(false)
  const [showApiKey, setShowApiKey] = useState(false)
  const [saving, setSaving] = useState(false)
  
  const [addingSecondaryModel, setAddingSecondaryModel] = useState(false)
  const [newSecondaryModel, setNewSecondaryModel] = useState({ provider: '', model_id: '' })

  useEffect(() => {
    if (agent && !synced) {
      const config = agent.config ?? {}
      setForm({
        model_provider: agent.model_provider ?? '',
        model_id: agent.model_id ?? '',
        token_budget: agent.token_budget ?? '',
        turn_token_cap: agent.turn_token_cap ?? '',
        max_retries: agent.max_retries ?? 3,
        fallback_agent_id: agent.fallback_agent_id ?? '',
        api_key: '',
        has_api_key: agent.has_api_key,
        api_key_mask: agent.api_key_mask,
        model_routing_enabled: agent.model_routing_enabled || false,
        secondary_models: agent.secondary_models || [],
        streaming_mode: config.streaming_mode || 'silent',
        pii_mesh_enabled: config.pii_mesh_enabled || false,
        pii_use_slm: config.pii_use_slm || false,
        tool_injection_strategy: config.tool_injection_strategy || 'auto',
      })
      setSynced(true)
    }
  }, [agent, synced])

  const setField = useCallback((field: string, value: any) => {
    setForm((prev) => ({ ...prev, [field]: value }))
  }, [])

  const handleClearApiKey = useCallback(() => {
    setField('api_key', '')
    setField('has_api_key', false)
    setField('api_key_mask', null)
  }, [setField])

  const addSecondaryModel = useCallback(() => {
    if (!newSecondaryModel.provider || !newSecondaryModel.model_id) return
    setField('secondary_models', [...(form.secondary_models || []), { ...newSecondaryModel, cost_tier: 'local' }])
    setNewSecondaryModel({ provider: '', model_id: '' })
    setAddingSecondaryModel(false)
  }, [newSecondaryModel, form.secondary_models, setField])

  const removeSecondaryModel = useCallback((index: number) => {
    const current = [...(form.secondary_models || [])]
    current.splice(index, 1)
    setField('secondary_models', current)
  }, [form.secondary_models, setField])

  const isDirty = useMemo(() => {
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
      Boolean(form.pii_use_slm) !== Boolean(agentConfig.pii_use_slm) ||
      String(form.tool_injection_strategy || 'auto') !== String(agentConfig.tool_injection_strategy || 'auto')
    )
  }, [form, agent])

  const handleSave = () => {
    if (!agent) return
    setSaving(true)
    
    const payload: Partial<Agent> = {}
    payload.model_provider = String(form.model_provider || '').trim() || null
    payload.model_id = String(form.model_id || '').trim() || null
    
    const fallback = String(form.fallback_agent_id || '').trim()
    payload.fallback_agent_id = fallback || null

    const tokenBudget = Number(form.token_budget)
    payload.token_budget = (!Number.isNaN(tokenBudget) && tokenBudget > 0) ? tokenBudget : null
    
    const turnTokenCap = Number(form.turn_token_cap)
    payload.turn_token_cap = (!Number.isNaN(turnTokenCap) && turnTokenCap > 0) ? turnTokenCap : null
    
    const maxRetries = Number(form.max_retries)
    payload.max_retries = !Number.isNaN(maxRetries) ? maxRetries : 3
    
    const apiKey = String(form.api_key || '').trim()
    if (apiKey) payload.api_key = apiKey
    else if (form.has_api_key === false) payload.api_key = null

    payload.model_routing_enabled = Boolean(form.model_routing_enabled)
    payload.secondary_models = Array.isArray(form.secondary_models) ? form.secondary_models : []

    const config = { ...(agent.config || {}) }
    config.streaming_mode = String(form.streaming_mode || 'silent')
    config.pii_mesh_enabled = Boolean(form.pii_mesh_enabled)
    config.pii_use_slm = Boolean(form.pii_use_slm)
    config.tool_injection_strategy = String(form.tool_injection_strategy || 'auto')
    payload.config = config

    updateAgent.mutate(
      { id: agent.id, payload },
      { 
        onSettled: () => {
          setSaving(false)
          setSynced(false) // Trigger re-sync from updated agent
        } 
      }
    )
  }

  const handleDiscard = () => {
    setSynced(false)
  }

  if (!agent && !agentsLoading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-bg-base p-8">
        <Zap className="w-16 h-16 text-accent-red mb-4" />
        <h1 className="text-2xl font-display font-bold text-text-primary">Agent Not Found</h1>
        <p className="text-text-secondary mt-2 mb-8">The agent you are looking for does not exist or has been deleted.</p>
        <Link to="/agents">
          <Button>Back to Agents</Button>
        </Link>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto bg-bg-base">
      <div className="p-6 md:p-8 max-w-4xl mx-auto space-y-8">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 pb-8 border-b border-border-dim">
          <div className="space-y-4">
            <Link
              to={`/agents/${id}`}
              className="inline-flex items-center gap-2 text-[10px] font-bold text-text-muted hover:text-accent-cyan transition-colors uppercase tracking-[0.2em]"
            >
              <ChevronLeft className="w-3 h-3" />
              Back to Agent
            </Link>
            <div className="space-y-1">
              <h1 className="text-3xl font-display font-bold text-text-primary tracking-tight uppercase flex items-center gap-4">
                <Zap className="w-8 h-8 text-accent-cyan" />
                Model Strategy
              </h1>
              <p className="text-text-secondary text-sm uppercase tracking-widest">
                Configure reasoning engines and safety protocols
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            {isDirty && (
              <Button
                variant="ghost"
                onClick={handleDiscard}
                disabled={saving}
                className="text-text-muted hover:text-text-primary rounded-none px-6"
              >
                DISCARD
              </Button>
            )}
            <Button
              onClick={handleSave}
              disabled={saving || !isDirty}
              className={cn(
                "rounded-none px-8 font-bold text-xs tracking-widest",
                isDirty ? "bg-accent-cyan text-black hover:opacity-90" : "bg-bg-surface text-text-muted border border-border-bright"
              )}
            >
              {saving ? 'SYNCING...' : isDirty ? 'COMMIT_CHANGES' : 'UP_TO_DATE'}
            </Button>
          </div>
        </div>

        {/* Content */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
           {/* Primary Model Card */}
           <div className="space-y-6">
             <div className="space-y-1">
               <h2 className="text-sm font-bold tracking-[0.2em] text-text-secondary uppercase flex items-center gap-3">
                 <Zap className="w-4 h-4" />
                 01 // PRIMARY_ENGINE
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
                   onChange={(e) => setField('streaming_mode', e.target.value)}
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
                 <Label className="text-[10px] tracking-widest text-text-muted uppercase">Tool Injection Strategy</Label>
                 <Select
                   value={String(form.tool_injection_strategy || 'auto')}
                   onChange={(e) => setField('tool_injection_strategy', e.target.value)}
                   className="bg-bg-surface border-border-bright focus:border-accent-cyan text-text-primary rounded-none h-12"
                 >
                   <option value="auto">AUTO (Filter + Fallback)</option>
                   <option value="all">ALL (Skip Filtering)</option>
                   <option value="strict">STRICT (Filter Only)</option>
                 </Select>
                 <p className="text-[9px] text-text-muted uppercase tracking-wider">
                   Controls how many tools are exposed to the LLM on each turn.
                 </p>
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
             </div>
           </div>

           {/* Limits and Safety Card */}
           <div className="space-y-12">
             <div className="space-y-6">
               <div className="space-y-1">
                 <h2 className="text-sm font-bold tracking-[0.2em] text-text-secondary uppercase flex items-center gap-3">
                   <ShieldAlert className="w-4 h-4" />
                   02 // LIMITS_AND_SAFETY
                 </h2>
                 <div className="h-px bg-border-dim w-full" />
               </div>

               <div className="p-8 border border-border-bright bg-bg-surface space-y-6">
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
                                type="button"
                                onClick={() => setAddingSecondaryModel(false)}
                                className="text-[10px] text-text-muted hover:text-text-primary uppercase tracking-widest"
                               >
                                CANCEL
                               </button>
                               <button
                                type="button"
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
               </div>
             </div>
           </div>
        </div>
      </div>
    </div>
  )
}
