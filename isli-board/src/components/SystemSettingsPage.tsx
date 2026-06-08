import { useState, useCallback, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useSettings, useUpdateSetting } from '@/hooks/useSettings'
import { ChevronLeft, Shield, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

interface SettingField {
  key: string
  label: string
  description: string
  type: 'number' | 'text' | 'boolean'
}

const PII_GROUP: SettingField[] = [
  {
    key: 'pii_mesh_default_enabled',
    label: 'PII Mesh Default',
    description: 'Default value for pii_mesh_enabled on newly created agents.',
    type: 'boolean',
  },
  {
    key: 'pii_use_slm_default',
    label: 'Use Keeper SLM Default',
    description: 'Default value for pii_use_slm on newly created agents.',
    type: 'boolean',
  },
  {
    key: 'pii_regex_pre_filter',
    label: 'Regex Pre-Filter',
    description: 'Enable fast regex pre-filtering before SLM inference for PII detection.',
    type: 'boolean',
  },
  {
    key: 'pii_token_ttl_hours',
    label: 'Token Map TTL (hours)',
    description: 'How long PII token maps are retained in the Keeper vault.',
    type: 'number',
  },
]

const INFRA_GROUP: SettingField[] = [
  {
    key: 'keeper_timeout_seconds',
    label: 'Keeper Timeout',
    description: 'HTTP timeout for calls to the Keeper sidecar.',
    type: 'number',
  },
  {
    key: 'agent_spawn_timeout_seconds',
    label: 'Agent Spawn Timeout',
    description: 'Seconds to wait for a new agent container to become healthy.',
    type: 'number',
  },
]

function SettingRow({
  field,
  value,
  onChange,
  saving,
}: {
  field: SettingField
  value: unknown
  onChange: (key: string, val: unknown) => void
  saving: boolean
}) {
  const [localValue, setLocalValue] = useState<string>(
    value !== undefined && value !== null ? String(value) : ''
  )

  useEffect(() => {
    setLocalValue(value !== undefined && value !== null ? String(value) : '')
  }, [value])

  const handleBlur = () => {
    let parsed: unknown = localValue
    if (field.type === 'number') {
      const n = Number(localValue)
      parsed = isNaN(n) ? value : n
    } else if (field.type === 'boolean') {
      parsed = localValue === 'true'
    }
    if (parsed !== value) {
      onChange(field.key, parsed)
    }
  }

  const handleToggle = () => {
    const next = !Boolean(value)
    onChange(field.key, next)
  }

  if (field.type === 'boolean') {
    return (
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 py-3 border-b border-border-dim/50 last:border-0">
        <div className="flex-1 min-w-0">
          <h3 className="text-xs font-semibold text-text-primary">{field.label}</h3>
          <p className="text-[11px] text-text-muted mt-0.5">{field.description}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {saving && <Loader2 className="w-3.5 h-3.5 text-accent-cyan animate-spin" />}
          <button
            type="button"
            onClick={handleToggle}
            disabled={saving}
            className={cn(
              'relative inline-flex h-5 w-9 items-center rounded-none transition-colors border',
              Boolean(value)
                ? 'border-accent-cyan bg-accent-cyan/10'
                : 'border-border-bright bg-bg-elevated'
            )}
          >
            <span
              className={cn(
                'inline-block h-3 w-3 transform rounded-none transition-transform',
                Boolean(value) ? 'translate-x-5 bg-accent-cyan' : 'translate-x-1 bg-text-muted'
              )}
            />
          </button>
        </div>
      </div>
    )
  }

  const inputClass = cn(
    'w-40 bg-bg-surface border border-border-dim rounded-lg px-3 py-2 text-sm text-text-primary',
    'focus:outline-none focus:border-accent-cyan/50 focus:ring-2 focus:ring-accent-cyan/10',
    'hover:border-border-bright transition-all duration-200',
    saving && 'opacity-60 cursor-wait'
  )

  return (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 py-3 border-b border-border-dim/50 last:border-0">
      <div className="flex-1 min-w-0">
        <h3 className="text-xs font-semibold text-text-primary">{field.label}</h3>
        <p className="text-[11px] text-text-muted mt-0.5">{field.description}</p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {saving && <Loader2 className="w-3.5 h-3.5 text-accent-cyan animate-spin" />}
        {field.type === 'number' ? (
          <input
            type="number"
            className={inputClass}
            value={localValue}
            onChange={(e) => setLocalValue(e.target.value)}
            onBlur={handleBlur}
            disabled={saving}
          />
        ) : (
          <input
            type="text"
            className={cn(inputClass, 'w-56 sm:w-64')}
            value={localValue}
            onChange={(e) => setLocalValue(e.target.value)}
            onBlur={handleBlur}
            disabled={saving}
          />
        )}
      </div>
    </div>
  )
}

function SettingGroup({
  title,
  fields,
  values,
  onChange,
  savingKey,
}: {
  title: string
  fields: SettingField[]
  values: Record<string, unknown>
  onChange: (key: string, val: unknown) => void
  savingKey: string | null
}) {
  return (
    <div className="bg-bg-surface border border-border-dim rounded-xl p-5">
      <h2 className="text-xs font-display font-bold uppercase tracking-widest text-text-primary mb-4">
        {title}
      </h2>
      <div className="space-y-1">
        {fields.map((field) => (
          <SettingRow
            key={field.key}
            field={field}
            value={values[field.key]}
            onChange={onChange}
            saving={savingKey === field.key}
          />
        ))}
      </div>
    </div>
  )
}

export function SystemSettingsPage() {
  const { data: settings = [], isLoading } = useSettings('system')
  const updateSetting = useUpdateSetting()
  const [savingKey, setSavingKey] = useState<string | null>(null)

  const values: Record<string, unknown> = {}
  for (const s of settings) {
    values[s.key] = s.value
  }

  const handleChange = useCallback(
    (key: string, val: unknown) => {
      setSavingKey(key)
      updateSetting.mutate(
        { key, value: val },
        {
          onSettled: () => setSavingKey(null),
        }
      )
    },
    [updateSetting]
  )

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-base">
        <div className="w-8 h-8 border-2 border-accent-cyan/20 border-t-accent-cyan rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto bg-bg-base h-full w-full min-h-0">
      <div className="p-6 md:p-8 max-w-4xl mx-auto space-y-8">
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
            <div className="w-10 h-10 rounded-xl bg-accent-amber/10 border border-accent-amber/20 flex items-center justify-center text-accent-amber">
              <Shield className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-sm font-display font-bold text-text-primary uppercase tracking-wider">
                System & Environment
              </h1>
              <p className="text-[10px] text-text-muted font-mono-data">
                Global compliance knobs, infrastructure timeouts, and PII defaults
              </p>
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <SettingGroup
            title="PII Mesh Defaults"
            fields={PII_GROUP}
            values={values}
            onChange={handleChange}
            savingKey={savingKey}
          />

          <SettingGroup
            title="Infrastructure"
            fields={INFRA_GROUP}
            values={values}
            onChange={handleChange}
            savingKey={savingKey}
          />
        </div>
      </div>
    </div>
  )
}
