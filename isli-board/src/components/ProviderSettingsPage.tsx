import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useProviders, useUpdateProvider, useAddPermittedModel, useRemovePermittedModel } from '@/hooks/useProviders'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { ChevronLeft, Zap, Eye, EyeOff, Plus, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'

export function ProviderSettingsPage() {
  const { data: providers = [], isLoading } = useProviders()
  const updateProvider = useUpdateProvider()
  const addModel = useAddPermittedModel()
  const removeModel = useRemovePermittedModel()

  const [showKey, setShowKey] = useState<Record<string, boolean>>({})
  const [keyInputs, setKeyInputs] = useState<Record<string, string>>({})
  const [baseInputs, setBaseInputs] = useState<Record<string, string>>({})
  const [modelInputs, setModelInputs] = useState<Record<string, { model_id: string; name: string }>>({})
  const [newProviderName, setNewProviderName] = useState('')

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-base">
        <div className="w-8 h-8 border-2 border-accent-cyan/20 border-t-accent-cyan rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto bg-bg-base h-full w-full min-h-0">
      <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-8">
        {/* Header */}
        <div className="flex flex-col gap-4">
          <Link
            to="/settings"
            className="flex items-center gap-2 text-xs font-display font-bold uppercase tracking-widest text-text-muted hover:text-accent-cyan transition-colors w-fit"
          >
            <ChevronLeft className="w-4 h-4" />
            Back to Settings
          </Link>
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-xl bg-accent-cyan/10 border border-accent-cyan/20 flex items-center justify-center text-accent-cyan">
              <Zap className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-sm font-display font-bold text-text-primary uppercase tracking-wider">
                Model API Keys
              </h1>
              <p className="text-[10px] text-text-muted font-mono-data">
                Configure provider keys and permitted models
              </p>
            </div>
          </div>
        </div>

        {/* Provider Cards */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {providers.map((provider) => (
            <div
              key={provider.provider}
              className="bg-bg-surface border border-border-dim rounded-xl overflow-hidden shadow-card"
            >
              {/* Card Header */}
              <div className="px-5 py-4 border-b border-border-dim bg-bg-elevated/30 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-display font-bold uppercase tracking-widest text-text-primary">
                    {provider.provider}
                  </span>
                  <span
                    className={cn(
                      'text-[9px] font-mono-data uppercase tracking-wider px-2 py-0.5 rounded',
                      provider.enabled
                        ? 'bg-accent-green/10 text-accent-green'
                        : 'bg-accent-red/10 text-accent-red'
                    )}
                  >
                    {provider.enabled ? 'Enabled' : 'Disabled'}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    updateProvider.mutate({
                      provider: provider.provider,
                      payload: { enabled: !provider.enabled },
                    })
                  }
                  disabled={updateProvider.isPending}
                  className={cn(
                    'w-10 h-6 rounded-full transition-colors relative',
                    provider.enabled ? 'bg-accent-cyan' : 'bg-bg-elevated border border-border-dim'
                  )}
                >
                  <div
                    className={cn(
                      'w-4 h-4 rounded-full bg-white absolute top-1 transition-all',
                      provider.enabled ? 'left-5' : 'left-1'
                    )}
                  />
                </button>
              </div>

              <div className="p-5 space-y-5">
                {/* API Key */}
                <div className="space-y-2">
                  <label className="text-[10px] font-display uppercase tracking-wider text-text-muted font-bold">
                    API Key
                  </label>
                  <div className="flex gap-2">
                    <div className="relative flex-1">
                      <Input
                        type={showKey[provider.provider] ? 'text' : 'password'}
                        value={
                          keyInputs[provider.provider] ??
                          (provider.has_api_key ? '••••••••••••' : '')
                        }
                        onChange={(e) =>
                          setKeyInputs((prev) => ({
                            ...prev,
                            [provider.provider]: e.target.value,
                          }))
                        }
                        placeholder="Enter API key..."
                        className="bg-bg-base/50 pr-10"
                      />
                      <button
                        type="button"
                        onClick={() =>
                          setShowKey((prev) => ({
                            ...prev,
                            [provider.provider]: !prev[provider.provider],
                          }))
                        }
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary transition-colors"
                      >
                        {showKey[provider.provider] ? (
                          <EyeOff className="w-3.5 h-3.5" />
                        ) : (
                          <Eye className="w-3.5 h-3.5" />
                        )}
                      </button>
                    </div>
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => {
                        const key = keyInputs[provider.provider]
                        if (!key || key === '••••••••••••') return
                        updateProvider.mutate(
                          {
                            provider: provider.provider,
                            payload: { api_key: key },
                          },
                          {
                            onSuccess: () =>
                              setKeyInputs((prev) => ({
                                ...prev,
                                [provider.provider]: '',
                              })),
                          }
                        )
                      }}
                      disabled={
                        !keyInputs[provider.provider] ||
                        keyInputs[provider.provider] === '••••••••••••'
                      }
                    >
                      Save Key
                    </Button>
                  </div>
                  {provider.has_api_key && (
                    <p className="text-[10px] text-text-muted font-mono-data">
                      Current: {provider.api_key_mask}
                    </p>
                  )}
                </div>

                {/* API Base */}
                <div className="space-y-2">
                  <label className="text-[10px] font-display uppercase tracking-wider text-text-muted font-bold">
                    API Base URL
                  </label>
                  <div className="flex gap-2">
                    <Input
                      value={baseInputs[provider.provider] ?? provider.api_base ?? ''}
                      onChange={(e) =>
                        setBaseInputs((prev) => ({
                          ...prev,
                          [provider.provider]: e.target.value,
                        }))
                      }
                      placeholder="e.g. http://localhost:11434/v1"
                      className="bg-bg-base/50 flex-1"
                    />
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => {
                        const base = baseInputs[provider.provider]
                        if (base === undefined) return
                        updateProvider.mutate(
                          {
                            provider: provider.provider,
                            payload: { api_base: base },
                          },
                          {
                            onSuccess: () =>
                              setBaseInputs((prev) => {
                                const next = { ...prev }
                                delete next[provider.provider]
                                return next
                              }),
                          }
                        )
                      }}
                      disabled={baseInputs[provider.provider] === undefined || updateProvider.isPending}
                    >
                      Save
                    </Button>
                  </div>
                  {provider.api_base && (
                    <p className="text-[10px] text-text-muted font-mono-data">
                      Active: {provider.api_base}
                    </p>
                  )}
                </div>

                {/* Models List */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-[10px] font-display uppercase tracking-wider text-text-muted font-bold">
                      Permitted Models
                    </label>
                    <span className="text-[10px] text-text-muted font-mono-data">
                      {provider.models.length}
                    </span>
                  </div>

                  <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1 custom-scrollbar">
                    {provider.models.length === 0 && (
                      <p className="text-[11px] text-text-muted italic py-2">
                        No models configured yet.
                      </p>
                    )}
                    {provider.models.map((model) => (
                      <div
                        key={model.id}
                        className="flex items-center justify-between bg-bg-elevated border border-border-dim rounded-lg px-3 py-2"
                      >
                        <div className="min-w-0">
                          <div className="text-[11px] font-mono-data text-text-primary truncate">
                            {model.name || model.model_id}
                          </div>
                          <div className="text-[10px] text-text-muted truncate">
                            {model.model_id}
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() =>
                            removeModel.mutate({
                              provider: provider.provider,
                              modelId: model.model_id,
                            })
                          }
                          disabled={removeModel.isPending}
                          className="ml-2 text-text-muted hover:text-accent-red transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>

                  {/* Add Model */}
                  <div className="flex gap-2 pt-1">
                    <Input
                      placeholder="Model ID"
                      value={modelInputs[provider.provider]?.model_id ?? ''}
                      onChange={(e) =>
                        setModelInputs((prev) => ({
                          ...prev,
                          [provider.provider]: {
                            ...prev[provider.provider],
                            model_id: e.target.value,
                          },
                        }))
                      }
                      className="flex-1 bg-bg-base/50 text-[11px]"
                    />
                    <Input
                      placeholder="Name (optional)"
                      value={modelInputs[provider.provider]?.name ?? ''}
                      onChange={(e) =>
                        setModelInputs((prev) => ({
                          ...prev,
                          [provider.provider]: {
                            ...prev[provider.provider],
                            name: e.target.value,
                          },
                        }))
                      }
                      className="flex-1 bg-bg-base/50 text-[11px]"
                    />
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => {
                        const input = modelInputs[provider.provider]
                        if (!input?.model_id?.trim()) return
                        addModel.mutate(
                          {
                            provider: provider.provider,
                            payload: {
                              model_id: input.model_id.trim(),
                              name: input.name?.trim() || null,
                            },
                          },
                          {
                            onSuccess: () =>
                              setModelInputs((prev) => ({
                                ...prev,
                                [provider.provider]: { model_id: '', name: '' },
                              })),
                          }
                        )
                      }}
                      disabled={!modelInputs[provider.provider]?.model_id?.trim()}
                    >
                      <Plus className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          ))}

          {/* Add New Provider Card */}
          <div className="bg-bg-surface border border-border-dim border-dashed rounded-xl overflow-hidden flex flex-col items-center justify-center p-8 space-y-4 hover:border-accent-cyan/40 transition-colors group">
            <div className="w-12 h-12 rounded-2xl bg-bg-elevated border border-border-dim flex items-center justify-center text-text-muted group-hover:text-accent-cyan group-hover:bg-accent-cyan/5 transition-all">
              <Plus className="w-6 h-6" />
            </div>
            <div className="text-center space-y-1">
              <h3 className="text-xs font-display font-bold text-text-primary uppercase tracking-wider">
                Add New Provider
              </h3>
              <p className="text-[10px] text-text-muted font-mono-data">
                Register a new LLM provider name
              </p>
            </div>
            <div className="w-full max-w-[240px] flex flex-col gap-2">
              <Input
                placeholder="Provider (e.g. anthropic)"
                value={newProviderName}
                onChange={(e) => setNewProviderName(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ''))}
                className="bg-bg-base/50 text-center font-mono-data text-xs"
              />
              <Button
                variant="primary"
                className="w-full"
                disabled={!newProviderName || updateProvider.isPending}
                onClick={() => {
                  updateProvider.mutate(
                    {
                      provider: newProviderName,
                      payload: { enabled: true },
                    },
                    {
                      onSuccess: () => setNewProviderName(''),
                    }
                  )
                }}
              >
                Add Provider
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
