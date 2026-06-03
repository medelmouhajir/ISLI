import { useState, useCallback, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useSettings, useUpdateSetting } from '@/hooks/useSettings'
import { ChevronLeft, SlidersHorizontal, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

interface SettingField {
  key: string
  label: string
  description: string
  type: 'number' | 'text'
}

const SESSION_GROUP: SettingField[] = [
  {
    key: 'session_idle_timeout_minutes',
    label: 'Session Idle Timeout',
    description: 'Minutes of inactivity before a session is soft-deleted.',
    type: 'number',
  },
  {
    key: 'task_lease_minutes',
    label: 'Task Lease Duration',
    description: 'Anti-zombie lease duration for claimed tasks.',
    type: 'number',
  },
  {
    key: 'delegation_max_depth',
    label: 'Max Delegation Depth',
    description: 'Maximum task delegation depth before blocking.',
    type: 'number',
  },
  {
    key: 'delegation_approval_depth',
    label: 'Approval Depth',
    description: 'Depth at which human approval is required for delegation.',
    type: 'number',
  },
]

const RESILIENCE_GROUP: SettingField[] = [
  {
    key: 'default_max_retries',
    label: 'Max Retries',
    description: 'Default max retries for exponential backoff and DLQ.',
    type: 'number',
  },
  {
    key: 'default_base_delay_seconds',
    label: 'Base Delay (seconds)',
    description: 'Base delay for exponential backoff retries.',
    type: 'number',
  },
  {
    key: 'default_max_delay_seconds',
    label: 'Max Delay (seconds)',
    description: 'Maximum delay cap for exponential backoff retries.',
    type: 'number',
  },
  {
    key: 'circuit_breaker_failure_threshold',
    label: 'Circuit Breaker Failure Threshold',
    description: 'Consecutive failures before circuit breaker opens.',
    type: 'number',
  },
  {
    key: 'circuit_breaker_recovery_timeout',
    label: 'Circuit Breaker Recovery (seconds)',
    description: 'Seconds before circuit breaker transitions to half-open.',
    type: 'number',
  },
]

const LOAD_GROUP: SettingField[] = [
  {
    key: 'bulkhead_max_queue',
    label: 'Bulkhead Max Queue',
    description: 'Maximum queue size for bulkhead per-agent/per-skill limits.',
    type: 'number',
  },
  {
    key: 'bulkhead_timeout_seconds',
    label: 'Bulkhead Timeout (seconds)',
    description: 'Timeout for acquiring a slot in the bulkhead queue.',
    type: 'number',
  },
]

const CORS_FIELD: SettingField = {
  key: 'cors_origins',
  label: 'CORS Origins',
  description: 'Comma-separated allowed origins (empty = localhost defaults).',
  type: 'text',
}

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
    }
    if (parsed !== value) {
      onChange(field.key, parsed)
    }
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

export function GeneralSettingsPage() {
  const { data: settings = [], isLoading } = useSettings('general')
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
            <div className="w-10 h-10 rounded-xl bg-accent-cyan/10 border border-accent-cyan/20 flex items-center justify-center text-accent-cyan">
              <SlidersHorizontal className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-sm font-display font-bold text-text-primary uppercase tracking-wider">
                General Settings
              </h1>
              <p className="text-[10px] text-text-muted font-mono-data">
                Global application preferences and operational knobs
              </p>
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <SettingGroup
            title="Session & Delegation"
            fields={SESSION_GROUP}
            values={values}
            onChange={handleChange}
            savingKey={savingKey}
          />

          <SettingGroup
            title="Resilience & Retries"
            fields={RESILIENCE_GROUP}
            values={values}
            onChange={handleChange}
            savingKey={savingKey}
          />

          <SettingGroup
            title="Load Management"
            fields={LOAD_GROUP}
            values={values}
            onChange={handleChange}
            savingKey={savingKey}
          />

          <div className="bg-bg-surface border border-border-dim rounded-xl p-5">
            <h2 className="text-xs font-display font-bold uppercase tracking-widest text-text-primary mb-4">
              CORS Origins
            </h2>
            <SettingRow
              field={CORS_FIELD}
              value={values.cors_origins}
              onChange={handleChange}
              saving={savingKey === CORS_FIELD.key}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
