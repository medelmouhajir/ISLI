import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getJSON, postJSON } from '@/lib/api'
import type { ProviderSettings } from '@/types'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Button } from '@/components/ui/Button'
import { Textarea } from '@/components/ui/Textarea'
import { Bot, ArrowLeft, ArrowRight, UserPlus, Cpu, Zap, Database } from 'lucide-react'
import { cn } from '@/lib/utils'

type Step = 1 | 2 | 3

interface AgentFormData {
  id: string
  name: string
  description: string
  persona: string
  model_provider: string
  model_id: string
  token_budget: string
}

export function CreateAgentPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState<Step>(1)
  const [loading, setLoading] = useState(false)
  const [formData, setFormData] = useState<AgentFormData>({
    id: '',
    name: '',
    description: '',
    persona: '',
    model_provider: '',
    model_id: '',
    token_budget: '',
  })

  const { data: providers = [] } = useQuery({
    queryKey: ['providers'],
    queryFn: () => getJSON<ProviderSettings[]>('/v1/settings/providers'),
    staleTime: 0,
  })

  const enabledProviders = providers.filter((p) => p.enabled)
  const selectedProviderData = enabledProviders.find((p) => p.provider === formData.model_provider)
  const availableModels = selectedProviderData?.models.filter((m) => m.enabled) || []

  const updateField = (field: keyof AgentFormData, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }))
  }

  const handleProviderChange = (value: string) => {
    setFormData((prev) => ({ ...prev, model_provider: value, model_id: '' }))
  }

  const nextStep = () => setStep((s) => (s < 3 ? (s + 1) as Step : s))
  const prevStep = () => setStep((s) => (s > 1 ? (s - 1) as Step : s))

  const handleSubmit = async () => {
    setLoading(true)
    try {
      await postJSON('/v1/agents', {
        ...formData,
        id: formData.id || undefined,
        token_budget: formData.token_budget ? Number(formData.token_budget) : null,
      })
      navigate('/agents')
    } catch (err) {
      console.error('Failed to create agent:', err)
    } finally {
      setLoading(false)
    }
  }

  const renderTimeline = () => {
    const steps = [
      { id: 1, label: 'IDENTITY' },
      { id: 2, label: 'INTELLIGENCE' },
      { id: 3, label: 'PERSONA' },
    ]

    return (
      <div className="flex flex-col gap-6 mb-12">
        {steps.map((s) => (
          <div key={s.id} className="flex items-center gap-4 group">
            <div 
              className={cn(
                "w-10 h-10 border flex items-center justify-center transition-all duration-300",
                "font-mono tabular-nums text-sm",
                step === s.id 
                  ? "border-transparent bg-accent-cyan text-bg-base" 
                  : "border-border-dim text-text-muted group-hover:border-border-bright"
              )}
            >
              0{s.id}
            </div>
            <div className="flex flex-col">
              <span className={cn(
                "text-[10px] tracking-[0.2em] font-mono",
                step === s.id ? "text-accent-cyan" : "text-text-muted"
              )}>
                PHASE
              </span>
              <span className={cn(
                "text-sm font-mono tracking-wider",
                step === s.id ? "text-text-primary" : "text-text-secondary"
              )}>
                {s.label}
              </span>
            </div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="flex-1 bg-bg-base flex flex-col font-mono overflow-hidden">
      {/* Top Header/Status Bar */}
      <div className="h-12 border-b border-border-dim flex items-center justify-between px-6 bg-bg-base">
        <div className="flex items-center gap-4">
          <button 
            onClick={() => navigate('/agents')}
            className="text-text-secondary hover:text-text-primary transition-colors flex items-center gap-2 text-xs tracking-widest"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            BACK
          </button>
          <div className="h-4 w-px bg-border-dim" />
          <h1 className="text-xs tracking-[0.3em] font-bold text-text-secondary">AGENT_ASSEMBLY_v1.0</h1>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 bg-accent-cyan animate-pulse" />
            <span className="text-[10px] text-accent-cyan tracking-widest">ONLINE</span>
          </div>
          <div className="h-4 w-px bg-border-dim" />
          <span className="text-[10px] text-text-muted tabular-nums uppercase">SYSTEM:OK</span>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* Navigation Sidebar */}
        <div className="w-64 border-r border-border-dim p-8 hidden md:block bg-bg-surface/50">
          {renderTimeline()}
          
          <div className="mt-auto pt-8 border-t border-border-dim">
            <p className="text-[10px] leading-relaxed text-text-muted uppercase tracking-tight">
              Establishing node parameters...
              <br />
              Allocating memory buffers...
              <br />
              Binding specialized skills...
            </p>
          </div>
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto p-6 md:p-12 lg:p-20">
          <div className="max-w-2xl mx-auto">
            {step === 1 && (
              <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
                <div className="space-y-2">
                  <h2 className="text-2xl font-bold tracking-tight text-text-primary flex items-center gap-3">
                    <Bot className="w-6 h-6 text-accent-cyan" />
                    01 // CORE_IDENTITY
                  </h2>
                  <p className="text-text-secondary text-sm">Define the primary parameters for the autonomous unit.</p>
                </div>

                <div className="grid grid-cols-1 gap-6">
                  <div className="space-y-1.5">
                    <label className="text-[10px] tracking-widest text-text-muted uppercase">Agent Name</label>
                    <Input 
                      value={formData.name}
                      onChange={(e) => updateField('name', e.target.value)}
                      placeholder="e.g. RESEARCHER_ALPHA"
                      className="bg-bg-surface border-border-dim focus:border-accent-cyan text-text-primary rounded-none h-12"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-[10px] tracking-widest text-text-muted uppercase">Serial ID (Optional)</label>
                    <Input 
                      value={formData.id}
                      onChange={(e) => updateField('id', e.target.value)}
                      placeholder="agent-001"
                      className="bg-bg-surface border-border-dim focus:border-accent-cyan text-text-primary rounded-none h-12"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-[10px] tracking-widest text-text-muted uppercase">Mission Description</label>
                    <Input 
                      value={formData.description}
                      onChange={(e) => updateField('description', e.target.value)}
                      placeholder="What is this unit's primary objective?"
                      className="bg-bg-surface border-border-dim focus:border-accent-cyan text-text-primary rounded-none h-12"
                    />
                  </div>
                </div>
              </div>
            )}

            {step === 2 && (
              <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
                <div className="space-y-2">
                  <h2 className="text-2xl font-bold tracking-tight text-text-primary flex items-center gap-3">
                    <Cpu className="w-6 h-6 text-accent-cyan" />
                    02 // INTELLIGENCE_LAYER
                  </h2>
                  <p className="text-text-secondary text-sm">Configure the reasoning engine and resource allocation.</p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-1.5">
                    <label className="text-[10px] tracking-widest text-text-muted uppercase">Model Provider</label>
                    <Select
                      value={formData.model_provider}
                      onChange={(e) => handleProviderChange(e.target.value)}
                      className="bg-bg-surface border-border-dim focus:border-accent-cyan text-text-primary rounded-none h-12"
                    >
                      <option value="">SELECT_PROVIDER</option>
                      {enabledProviders.map((p) => (
                        <option key={p.provider} value={p.provider}>{p.provider.toUpperCase()}</option>
                      ))}
                    </Select>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-[10px] tracking-widest text-text-muted uppercase">Model Specification</label>
                    <Select
                      value={formData.model_id}
                      onChange={(e) => updateField('model_id', e.target.value)}
                      disabled={!formData.model_provider}
                      className="bg-bg-surface border-border-dim focus:border-accent-cyan text-text-primary rounded-none h-12 disabled:opacity-30"
                    >
                      <option value="">{formData.model_provider ? 'SELECT_MODEL' : 'AWAITING_PROVIDER'}</option>
                      {availableModels.map((m) => (
                        <option key={m.model_id} value={m.model_id}>{m.name || m.model_id}</option>
                      ))}
                    </Select>
                  </div>

                  <div className="space-y-1.5 md:col-span-2">
                    <label className="text-[10px] tracking-widest text-text-muted uppercase">Token Budget (LIFETIME)</label>
                    <div className="relative">
                      <Input 
                        type="number"
                        value={formData.token_budget}
                        onChange={(e) => updateField('token_budget', e.target.value)}
                        placeholder="100000"
                        className="bg-bg-surface border-border-dim focus:border-accent-cyan text-text-primary rounded-none h-12 pl-12"
                      />
                      <Database className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted opacity-50" />
                    </div>
                  </div>
                </div>
              </div>
            )}

            {step === 3 && (
              <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
                <div className="space-y-2">
                  <h2 className="text-2xl font-bold tracking-tight text-text-primary flex items-center gap-3">
                    <Zap className="w-6 h-6 text-accent-cyan" />
                    03 // BEHAVIORAL_PERSONA
                  </h2>
                  <p className="text-text-secondary text-sm">Inject core logic, tone, and operational constraints.</p>
                </div>

                <div className="space-y-1.5">
                  <label className="text-[10px] tracking-widest text-text-muted uppercase">System Prompt / Persona</label>
                  <Textarea 
                    value={formData.persona}
                    onChange={(e) => updateField('persona', e.target.value)}
                    placeholder="ENTER_INSTRUCTIONS_HERE..."
                    rows={12}
                    className="bg-bg-surface border-border-dim focus:border-accent-cyan text-text-primary rounded-none resize-none font-mono text-sm leading-relaxed p-6 focus:ring-0"
                  />
                </div>
              </div>
            )}

            {/* Navigation Controls */}
            <div className="mt-12 flex items-center justify-between pt-8 border-t border-border-dim">
              <Button 
                variant="ghost" 
                onClick={prevStep}
                disabled={step === 1}
                className="text-text-secondary hover:text-text-primary rounded-none border-border-dim px-8 disabled:opacity-0"
              >
                PREV
              </Button>

              <div className="flex gap-4">
                {step < 3 ? (
                  <Button 
                    onClick={nextStep}
                    disabled={step === 1 && !formData.name}
                    className="bg-bg-surface text-text-primary hover:bg-bg-hover rounded-none border-border-dim px-8 group"
                  >
                    NEXT_STEP
                    <ArrowRight className="ml-2 w-4 h-4 group-hover:translate-x-1 transition-transform" />
                  </Button>
                ) : (
                  <Button 
                    onClick={handleSubmit}
                    disabled={loading || !formData.name}
                    className="bg-accent-cyan text-bg-base hover:opacity-90 rounded-none px-8 font-bold shadow-glow-cyan"
                  >
                    {loading ? 'INITIALIZING...' : 'FINALIZE_CONSTRUCTION'}
                    <UserPlus className="ml-2 w-4 h-4" />
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Footer Info */}
      <div className="h-10 border-t border-border-dim bg-bg-base flex items-center justify-between px-6">
         <div className="flex items-center gap-6">
            <span className="text-[9px] text-text-muted tracking-[0.2em]">LATENCY: 12ms</span>
            <span className="text-[9px] text-text-muted tracking-[0.2em]">LOAD: 0.12</span>
         </div>
         <span className="text-[9px] text-text-muted tracking-[0.2em] uppercase tabular-nums">ISLI_BOARD_v1.0.2</span>
      </div>
    </div>
  )
}
