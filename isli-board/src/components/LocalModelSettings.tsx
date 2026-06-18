import { useState, useEffect } from 'react'
import {
  Download,
  RefreshCw,
  Trash2,
  Zap,
  Cpu,
  Database,
  Activity,
  Layers,
  Info,
  ChevronRight,
  ShieldCheck,
  Mic,
  X,
  Plus,
  Settings,
  Check,
} from 'lucide-react'
import { getJSON, postJSON, putJSON, deleteJSON } from '../lib/api'
import { Button } from './ui/Button'
import { Badge } from './ui/Badge'
import { Label } from './ui/Label'
import { Toggle } from './ui/Toggle'
import { ConfirmationModal } from './ui/ConfirmationModal'
import { cn } from '@/lib/utils'

interface ModelStatus {
  current: { gen: string; embed: string; stt: string; tts: string }
  permitted: { gen: string[]; embed: string[]; stt: string[]; tts: string[] }
  available: { ollama: string[]; audio: string[] }
  status: string
}

interface KeeperConfig {
  gen: string
  embed: string
  num_ctx: number
  num_batch: number
  think: boolean
}

export function LocalModelSettings() {
  const [data, setData] = useState<ModelStatus | null>(null)
  const [keeperConfig, setKeeperConfig] = useState<KeeperConfig | null>(null)
  const [configSaved, setConfigSaved] = useState(false)
  const [loading, setLoading] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [newModelInputs, setNewModelInputs] = useState<Record<string, string>>({})
  const [confirmModal, setConfirmModal] = useState<{
    open: boolean;
    title: string;
    description: string;
    onConfirm: () => void | Promise<void>;
  }>({
    open: false,
    title: '',
    description: '',
    onConfirm: () => {},
  })

  const fetchStatus = async () => {
    try {
      const json = await getJSON<ModelStatus>('/v1/model-management/status')
      setData(json)
      setErrorMessage(null)
    } catch (err) {
      setErrorMessage('Failed to connect to model management service.')
      console.error(err)
    }
  }

  const fetchConfig = async () => {
    try {
      const json = await getJSON<{ config: KeeperConfig }>('/v1/model-management/config')
      setKeeperConfig({ ...json.config, think: json.config.think ?? false })
    } catch (err) {
      console.error('Failed to fetch keeper config:', err)
    }
  }

  useEffect(() => {
    fetchStatus()
    fetchConfig()
    const interval = setInterval(fetchStatus, 10000)
    return () => clearInterval(interval)
  }, [])

  const isPullInProgress = loading !== null && loading.startsWith('pull:')

  const handlePull = async (slot: string, model: string) => {
    setLoading(`pull:${slot}:${model}`)
    try {
      await postJSON('/v1/model-management/pull', { slot, model_name: model })
      fetchStatus()
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(null)
    }
  }

  const handleActivate = async (slot: string, model: string) => {
    setLoading(`activate:${slot}:${model}`)
    try {
      await postJSON('/v1/model-management/activate', { slot, model_name: model })
      fetchStatus()
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(null)
    }
  }

  const performRemove = async (model: string) => {
    setLoading(`remove:${model}`)
    try {
      await postJSON('/v1/model-management/remove', { model_name: model })
      fetchStatus()
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(null)
    }
  }

  const handleRemove = (model: string) => {
    setConfirmModal({
      open: true,
      title: 'Remove Local Model',
      description: `Are you sure you want to remove model "${model}" from the system? This will delete the model weights from disk and any agents using it will need to pull it again.`,
      onConfirm: () => performRemove(model),
    })
  }

  const handleUpdateConfig = async (updates: Partial<KeeperConfig>) => {
    setLoading('config:update')
    try {
      await putJSON('/v1/model-management/config', updates)
      setConfigSaved(true)
      setTimeout(() => setConfigSaved(false), 3000)
      await fetchConfig()
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(null)
    }
  }

  const handleAddPermitted = async (slot: string, model: string) => {
    setLoading(`add-permitted:${slot}:${model}`)
    try {
      await postJSON('/v1/model-management/permitted', { slot, model_name: model })
      await fetchStatus()
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(null)
    }
  }

  const handleRemovePermitted = async (slot: string, model: string) => {
    setLoading(`remove-permitted:${slot}:${model}`)
    try {
      await deleteJSON(`/v1/model-management/permitted/${slot}/${encodeURIComponent(model)}`)
      await fetchStatus()
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(null)
    }
  }

  if (!data && !errorMessage) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-base">
        <div className="flex flex-col items-center gap-4">
          <RefreshCw className="w-8 h-8 text-accent-cyan animate-spin" />
          <span className="text-[10px] font-mono text-text-muted uppercase tracking-widest">INITIALIZING_KEEPER_SUBSYSTEM...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto bg-bg-base p-6 md:p-8">
      <div className="max-w-7xl mx-auto space-y-8">
        {/* Header Section */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-border-dim pb-8">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <div className="w-2 h-2 rounded-none bg-accent-cyan animate-pulse" />
              <span className="text-[10px] font-mono font-bold text-accent-cyan uppercase tracking-[0.2em]">System_Management</span>
            </div>
            <h1 className="text-3xl font-display font-bold text-text-primary tracking-tight">KEEPER_MODELS</h1>
            <p className="text-text-secondary text-sm mt-2 max-w-2xl font-mono opacity-70">
              Manage local generative, embedding, and audio models for background intelligence.
              The Keeper subsystem utilizes Ollama as its primary execution engine; audio models run independently.
            </p>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex flex-col items-end">
              <Label className="mb-0">Engine_Status</Label>
              <Badge variant={data?.status === 'online' ? 'success' : 'danger'}>
                {data?.status?.toUpperCase() || 'OFFLINE'}
              </Badge>
            </div>
            <Button variant="secondary" size="sm" onClick={fetchStatus}>
              <RefreshCw className={cn("w-3.5 h-3.5 mr-2", !data && "animate-spin")} />
              Sync
            </Button>
          </div>
        </div>

        {errorMessage && (
          <div className="bg-accent-red/10 border border-accent-red/20 p-4 rounded-none flex items-center gap-3 animate-in fade-in slide-in-from-top-2">
            <ShieldCheck className="w-5 h-5 text-accent-red" />
            <p className="text-xs font-mono text-accent-red font-bold uppercase tracking-tight">{errorMessage}</p>
            <Button variant="ghost" size="sm" onClick={() => setErrorMessage(null)} className="ml-auto">Dismiss</Button>
          </div>
        )}

        {isPullInProgress && (
          <div className="bg-accent-amber/5 border border-accent-amber/20 p-4 rounded-none space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Download className="w-4 h-4 text-accent-amber animate-bounce" />
                <span className="text-[10px] font-mono font-bold text-accent-amber uppercase tracking-widest">Model_Transfer_In_Progress</span>
              </div>
              <span className="text-[10px] font-mono-data text-accent-amber">ACQUIRING_BLOBS...</span>
            </div>
            <div className="h-1 bg-accent-amber/10 w-full overflow-hidden">
              <div className="h-full bg-accent-amber w-1/3 animate-[slide-right_2s_infinite_linear]" />
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-8">
          <ModelModule
            slot="gen"
            title="Generative_Inference"
            folio="[KM-01-GEN]"
            icon={Cpu}
            description="High-density models for summarization and reasoning tasks."
            data={data}
            loading={loading}
            onPull={handlePull}
            onActivate={handleActivate}
            onRemove={handleRemove}
            onAddPermitted={handleAddPermitted}
            onRemovePermitted={handleRemovePermitted}
            newModelInputs={newModelInputs}
            setNewModelInputs={setNewModelInputs}
            isPullInProgress={isPullInProgress}
          />
          <ModelModule
            slot="embed"
            title="Semantic_Vectorization"
            folio="[KM-02-EMD]"
            icon={Layers}
            description="Specialized models for RAG and semantic search indexing."
            data={data}
            loading={loading}
            onPull={handlePull}
            onActivate={handleActivate}
            onRemove={handleRemove}
            onAddPermitted={handleAddPermitted}
            onRemovePermitted={handleRemovePermitted}
            newModelInputs={newModelInputs}
            setNewModelInputs={setNewModelInputs}
            isPullInProgress={isPullInProgress}
          />
          <AudioModule
            title="Audio_Processing"
            folio="[KM-03-AUD]"
            icon={Mic}
            description="Local speech-to-text and text-to-speech models for voice messaging."
            data={data}
            loading={loading}
            onPull={handlePull}
            onActivate={handleActivate}
            onRemove={handleRemove}
            onAddPermitted={handleAddPermitted}
            onRemovePermitted={handleRemovePermitted}
            newModelInputs={newModelInputs}
            setNewModelInputs={setNewModelInputs}
            isPullInProgress={isPullInProgress}
          />
        </div>

        {/* Generation Options */}
        <div className="max-w-7xl mx-auto space-y-8">
          <div className="card-surface flex flex-col">
            <div className="p-5 border-b border-border-dim bg-bg-elevated/30 flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-none bg-bg-surface border border-border-dim flex items-center justify-center text-text-primary">
                  <Settings className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-sm font-display font-bold text-text-primary uppercase tracking-wider">Generation_Options</h2>
                  <p className="text-[10px] font-mono text-text-muted uppercase tracking-widest mt-0.5">
                    Runtime inference parameters for the local Ollama engine.
                  </p>
                </div>
              </div>
              <span className="text-[10px] font-mono font-bold text-text-muted opacity-40">
                [KM-04-OPT]
              </span>
            </div>

            <div className="p-5 grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2">
                <Label className="text-[10px] font-mono font-bold uppercase tracking-widest">Context Length (num_ctx)</Label>
                <input
                  type="number"
                  min={512}
                  max={524288}
                  step={1024}
                  value={keeperConfig?.num_ctx ?? 4096}
                  onChange={e => {
                    const val = parseInt(e.target.value, 10)
                    if (!Number.isNaN(val)) {
                      setKeeperConfig(prev => prev ? { ...prev, num_ctx: val } : null)
                    }
                  }}
                  className="w-full bg-bg-surface border border-border-dim px-3 py-2 text-xs font-mono text-text-primary placeholder:text-text-muted/50 focus:outline-none focus:border-accent-cyan"
                />
                <p className="text-[9px] font-mono text-text-muted opacity-60">
                  Maximum tokens the model can attend to. Requires more RAM at higher values.
                </p>
              </div>

              <div className="space-y-2">
                <Label className="text-[10px] font-mono font-bold uppercase tracking-widest">Batch Size (num_batch)</Label>
                <input
                  type="number"
                  min={1}
                  max={4096}
                  step={512}
                  value={keeperConfig?.num_batch ?? 512}
                  onChange={e => {
                    const val = parseInt(e.target.value, 10)
                    if (!Number.isNaN(val)) {
                      setKeeperConfig(prev => prev ? { ...prev, num_batch: val } : null)
                    }
                  }}
                  className="w-full bg-bg-surface border border-border-dim px-3 py-2 text-xs font-mono text-text-primary placeholder:text-text-muted/50 focus:outline-none focus:border-accent-cyan"
                />
                <p className="text-[9px] font-mono text-text-muted opacity-60">
                  Tokens processed in parallel. Higher values speed up inference but use more memory.
                </p>
              </div>

              <div className="space-y-2 md:col-span-2">
                <div className="flex items-center justify-between">
                  <Label className="text-[10px] font-mono font-bold uppercase tracking-widest">Thinking Mode</Label>
                  <Toggle
                    checked={keeperConfig?.think ?? false}
                    onChange={checked => {
                      setKeeperConfig(prev => prev ? { ...prev, think: checked } : null)
                    }}
                    label={keeperConfig?.think ? 'Enabled' : 'Disabled'}
                  />
                </div>
                <p className="text-[9px] font-mono text-text-muted opacity-60">
                  Disable thinking to stop the model emitting internal reasoning traces
                  (&lt;think&gt;...&lt;/think&gt;) and reduce latency for Keeper tasks.
                </p>
              </div>
            </div>

            <div className="px-5 py-3 border-t border-border-dim bg-bg-elevated/20 flex items-center justify-between">
              <div className="flex items-center gap-3">
                {configSaved && (
                  <div className="flex items-center gap-1.5 text-accent-green">
                    <Check className="w-3.5 h-3.5" />
                    <span className="text-[10px] font-mono font-bold uppercase tracking-widest">Saved</span>
                  </div>
                )}
              </div>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  if (keeperConfig) {
                    handleUpdateConfig({
                      num_ctx: keeperConfig.num_ctx,
                      num_batch: keeperConfig.num_batch,
                      think: keeperConfig.think,
                    })
                  }
                }}
                disabled={loading === 'config:update' || !keeperConfig}
                className="text-[10px] font-bold uppercase tracking-widest"
              >
                {loading === 'config:update' ? (
                  <RefreshCw className="animate-spin w-3.5 h-3.5 mr-2" />
                ) : (
                  <Zap className="w-3.5 h-3.5 mr-2" />
                )}
                Apply
              </Button>
            </div>
          </div>
        </div>
      </div>
      <ConfirmationModal
        open={confirmModal.open}
        title={confirmModal.title}
        description={confirmModal.description}
        variant="danger"
        confirmText="Remove Model"
        onConfirm={confirmModal.onConfirm}
        onClose={() => setConfirmModal(prev => ({ ...prev, open: false }))}
        isLoading={loading !== null && loading.startsWith('remove:')}
      />
    </div>
  )
}

interface ModelModuleProps {
  slot: 'gen' | 'embed'
  title: string
  folio: string
  icon: any
  description: string
  data: ModelStatus | null
  loading: string | null
  onPull: (slot: string, model: string) => void
  onActivate: (slot: string, model: string) => void
  onRemove: (model: string) => void
  onAddPermitted: (slot: string, model: string) => void
  onRemovePermitted: (slot: string, model: string) => void
  newModelInputs: Record<string, string>
  setNewModelInputs: React.Dispatch<React.SetStateAction<Record<string, string>>>
  isPullInProgress: boolean
}

function ModelModule({
  slot, title, folio, icon: Icon, description, data, loading, onPull, onActivate, onRemove,
  onAddPermitted, onRemovePermitted, newModelInputs, setNewModelInputs, isPullInProgress
}: ModelModuleProps) {
  if (!data) return null

  const inputValue = newModelInputs[slot] ?? ''
  const isAdding = loading?.startsWith(`add-permitted:${slot}:`) ?? false

  return (
    <div className="card-surface flex flex-col h-full group">
      <div className="p-5 border-b border-border-dim bg-bg-elevated/30 flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-none bg-bg-surface border border-border-dim flex items-center justify-center text-text-primary">
            <Icon className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-sm font-display font-bold text-text-primary uppercase tracking-wider">{title}</h2>
            <p className="text-[10px] font-mono text-text-muted uppercase tracking-widest mt-0.5">{description}</p>
          </div>
        </div>
        <span className="text-[10px] font-mono font-bold text-text-muted opacity-40 group-hover:opacity-100 transition-opacity">
          {folio}
        </span>
      </div>

      <div className="p-5 flex-1 space-y-4">
        <div className="space-y-3">
          {data.permitted[slot].map(model => {
            const isActive = data.current[slot] === model
            const isAvailable = data.available.ollama.includes(model)
            const isBusy = loading === `pull:${slot}:${model}` || loading === `activate:${slot}:${model}`
            const isRemoving = loading === `remove:${model}`
            const isRemovingPermitted = loading === `remove-permitted:${slot}:${model}`

            return (
              <div
                key={model}
                className={cn(
                  "border p-4 transition-all duration-200 flex flex-col gap-4",
                  isActive
                    ? "bg-accent-green/5 border-accent-green/30"
                    : isAvailable
                    ? "bg-bg-surface border-border-dim hover:border-border-bright"
                    : "bg-bg-base/30 border-border-dim/50 opacity-60"
                )}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={cn(
                      "w-1.5 h-1.5 rounded-none",
                      isActive ? "bg-accent-green" : isAvailable ? "bg-accent-cyan" : "bg-text-muted"
                    )} />
                    <span className="font-mono text-xs font-bold tracking-tight text-text-primary">{model}</span>
                    {isActive && (
                      <Badge variant="success" className="text-[9px] px-1.5 py-0">ACTIVE_PRIMARY</Badge>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    {isBusy ? (
                      <RefreshCw className="animate-spin w-4 h-4 text-accent-cyan" />
                    ) : isActive ? (
                      <Activity className="w-4 h-4 text-accent-green" />
                    ) : isAvailable ? (
                      <div className="flex items-center gap-1.5">
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => onActivate(slot, model)}
                          disabled={isPullInProgress || isRemoving}
                          title="Set as active model"
                          className="h-7 px-2"
                        >
                          <Zap className="w-3.5 h-3.5" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => onRemove(model)}
                          disabled={isPullInProgress || isRemoving}
                          title="Remove from system (delete weights)"
                          className="h-7 px-2 text-text-muted hover:text-accent-red"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => onRemovePermitted(slot, model)}
                          disabled={isPullInProgress || isRemoving || isRemovingPermitted}
                          title="Remove from permitted list"
                          className="h-7 px-2 text-text-muted hover:text-accent-amber"
                        >
                          <X className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5">
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => onPull(slot, model)}
                          disabled={isPullInProgress}
                          className="h-7 px-3 text-[10px] font-bold uppercase tracking-widest"
                        >
                          <Download className="w-3.5 h-3.5 mr-2" />
                          Pull
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => onRemovePermitted(slot, model)}
                          disabled={isPullInProgress || isRemovingPermitted}
                          title="Remove from permitted list"
                          className="h-7 px-2 text-text-muted hover:text-accent-amber"
                        >
                          <X className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    )}
                  </div>
                </div>

                {isAvailable && (
                  <div className="flex items-center gap-4 border-t border-border-dim pt-3 opacity-60">
                    <div className="flex items-center gap-1.5">
                      <Database className="w-3 h-3 text-text-muted" />
                      <span className="text-[9px] font-mono-data text-text-muted uppercase tracking-tighter">OLLAMA_BLOB_SYNCED</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Info className="w-3 h-3 text-text-muted" />
                      <span className="text-[9px] font-mono-data text-text-muted uppercase tracking-tighter">FP16_QUANTIZED</span>
                    </div>
                  </div>
                )}
              </div>
            )
          })}

          <div className="pt-2 space-y-2">
            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="ollama tag, e.g. gemma3:1b"
                value={inputValue}
                onChange={e => setNewModelInputs(prev => ({ ...prev, [slot]: e.target.value }))}
                onKeyDown={e => {
                  if (e.key === 'Enter' && inputValue.trim()) {
                    onAddPermitted(slot, inputValue.trim())
                    setNewModelInputs(prev => ({ ...prev, [slot]: '' }))
                  }
                }}
                disabled={isAdding}
                className="flex-1 bg-bg-surface border border-border-dim px-3 py-2 text-xs font-mono text-text-primary placeholder:text-text-muted/50 focus:outline-none focus:border-accent-cyan disabled:opacity-50"
              />
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  if (inputValue.trim()) {
                    onAddPermitted(slot, inputValue.trim())
                    setNewModelInputs(prev => ({ ...prev, [slot]: '' }))
                  }
                }}
                disabled={!inputValue.trim() || isAdding}
                className="h-8 px-3 text-[10px] font-bold uppercase tracking-widest"
              >
                {isAdding ? <RefreshCw className="animate-spin w-3.5 h-3.5" /> : <Plus className="w-3.5 h-3.5 mr-1" />}
                Add Model
              </Button>
            </div>
            <p className="text-[9px] font-mono text-text-muted opacity-60">
              Small local models only. Large models may exhaust container memory.
            </p>
          </div>
        </div>
      </div>

      <div className="px-5 py-3 border-t border-border-dim bg-bg-elevated/20 flex items-center justify-between">
        <span className="text-[9px] font-mono text-text-muted uppercase tracking-widest">Module_Security_Level: 01</span>
        <ChevronRight className="w-3 h-3 text-text-muted opacity-30" />
      </div>
    </div>
  )
}

interface AudioModuleProps {
  title: string
  folio: string
  icon: any
  description: string
  data: ModelStatus | null
  loading: string | null
  onPull: (slot: string, model: string) => void
  onActivate: (slot: string, model: string) => void
  onRemove: (model: string) => void
  onAddPermitted: (slot: string, model: string) => void
  onRemovePermitted: (slot: string, model: string) => void
  newModelInputs: Record<string, string>
  setNewModelInputs: React.Dispatch<React.SetStateAction<Record<string, string>>>
  isPullInProgress: boolean
}

function AudioModule({
  title, folio, icon: Icon, description, data, loading, onPull, onActivate, onRemove,
  onAddPermitted, onRemovePermitted, newModelInputs, setNewModelInputs, isPullInProgress
}: AudioModuleProps) {
  if (!data) return null

  const renderSlot = (slot: 'stt' | 'tts', label: string) => {
    const inputValue = newModelInputs[slot] ?? ''
    const isAdding = loading?.startsWith(`add-permitted:${slot}:`) ?? false

    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono font-bold text-text-muted uppercase tracking-widest">{label}</span>
          <div className="h-px flex-1 bg-border-dim" />
        </div>
        <div className="space-y-3">
          {data.permitted[slot].map(model => {
            const isActive = data.current[slot] === model
            const isAvailable = data.available.audio.includes(model)
            const isBusy = loading === `pull:${slot}:${model}` || loading === `activate:${slot}:${model}`
            const isRemoving = loading === `remove:${model}`
            const isRemovingPermitted = loading === `remove-permitted:${slot}:${model}`

            return (
              <div
                key={model}
                className={cn(
                  "border p-3 transition-all duration-200 flex flex-col gap-3",
                  isActive
                    ? "bg-accent-green/5 border-accent-green/30"
                    : isAvailable
                    ? "bg-bg-surface border-border-dim hover:border-border-bright"
                    : "bg-bg-base/30 border-border-dim/50 opacity-60"
                )}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={cn(
                      "w-1.5 h-1.5 rounded-none",
                      isActive ? "bg-accent-green" : isAvailable ? "bg-accent-cyan" : "bg-text-muted"
                    )} />
                    <span className="font-mono text-xs font-bold tracking-tight text-text-primary">{model}</span>
                    {isActive && (
                      <Badge variant="success" className="text-[9px] px-1.5 py-0">ACTIVE</Badge>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    {isBusy ? (
                      <RefreshCw className="animate-spin w-4 h-4 text-accent-cyan" />
                    ) : isActive ? (
                      <Activity className="w-4 h-4 text-accent-green" />
                    ) : isAvailable ? (
                      <div className="flex items-center gap-1.5">
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => onActivate(slot, model)}
                          disabled={isPullInProgress || isRemoving}
                          title="Set as active model"
                          className="h-6 px-2"
                        >
                          <Zap className="w-3 h-3" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => onRemove(model)}
                          disabled={isPullInProgress || isRemoving}
                          title="Remove from system (delete weights)"
                          className="h-6 px-2 text-text-muted hover:text-accent-red"
                        >
                          <Trash2 className="w-3 h-3" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => onRemovePermitted(slot, model)}
                          disabled={isPullInProgress || isRemoving || isRemovingPermitted}
                          title="Remove from permitted list"
                          className="h-6 px-2 text-text-muted hover:text-accent-amber"
                        >
                          <X className="w-3 h-3" />
                        </Button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5">
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => onPull(slot, model)}
                          disabled={isPullInProgress}
                          className="h-6 px-3 text-[10px] font-bold uppercase tracking-widest"
                        >
                          <Download className="w-3 h-3 mr-2" />
                          Pull
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => onRemovePermitted(slot, model)}
                          disabled={isPullInProgress || isRemovingPermitted}
                          title="Remove from permitted list"
                          className="h-6 px-2 text-text-muted hover:text-accent-amber"
                        >
                          <X className="w-3 h-3" />
                        </Button>
                      </div>
                    )}
                  </div>
                </div>

                {isAvailable && (
                  <div className="flex items-center gap-4 border-t border-border-dim pt-2 opacity-60">
                    <div className="flex items-center gap-1.5">
                      <Database className="w-3 h-3 text-text-muted" />
                      <span className="text-[9px] font-mono-data text-text-muted uppercase tracking-tighter">LOCAL_ONNX</span>
                    </div>
                  </div>
                )}
              </div>
            )
          })}

          <div className="pt-2 space-y-2">
            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="model name, e.g. whisper-base"
                value={inputValue}
                onChange={e => setNewModelInputs(prev => ({ ...prev, [slot]: e.target.value }))}
                onKeyDown={e => {
                  if (e.key === 'Enter' && inputValue.trim()) {
                    onAddPermitted(slot, inputValue.trim())
                    setNewModelInputs(prev => ({ ...prev, [slot]: '' }))
                  }
                }}
                disabled={isAdding}
                className="flex-1 bg-bg-surface border border-border-dim px-3 py-2 text-xs font-mono text-text-primary placeholder:text-text-muted/50 focus:outline-none focus:border-accent-cyan disabled:opacity-50"
              />
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  if (inputValue.trim()) {
                    onAddPermitted(slot, inputValue.trim())
                    setNewModelInputs(prev => ({ ...prev, [slot]: '' }))
                  }
                }}
                disabled={!inputValue.trim() || isAdding}
                className="h-7 px-3 text-[10px] font-bold uppercase tracking-widest"
              >
                {isAdding ? <RefreshCw className="animate-spin w-3 h-3" /> : <Plus className="w-3 h-3 mr-1" />}
                Add Model
              </Button>
            </div>
            <p className="text-[9px] font-mono text-text-muted opacity-60">
              Audio model names are validated by the Audio service on pull.
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="card-surface flex flex-col h-full group">
      <div className="p-5 border-b border-border-dim bg-bg-elevated/30 flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-none bg-bg-surface border border-border-dim flex items-center justify-center text-text-primary">
            <Icon className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-sm font-display font-bold text-text-primary uppercase tracking-wider">{title}</h2>
            <p className="text-[10px] font-mono text-text-muted uppercase tracking-widest mt-0.5">{description}</p>
          </div>
        </div>
        <span className="text-[10px] font-mono font-bold text-text-muted opacity-40 group-hover:opacity-100 transition-opacity">
          {folio}
        </span>
      </div>

      <div className="p-5 flex-1 space-y-6">
        {renderSlot('stt', 'Speech-to-Text')}
        {renderSlot('tts', 'Text-to-Speech')}
      </div>

      <div className="px-5 py-3 border-t border-border-dim bg-bg-elevated/20 flex items-center justify-between">
        <span className="text-[9px] font-mono text-text-muted uppercase tracking-widest">Module_Security_Level: 01</span>
        <ChevronRight className="w-3 h-3 text-text-muted opacity-30" />
      </div>
    </div>
  )
}
