import { useState, useCallback, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useSettings, useUpdateSetting } from '@/hooks/useSettings'
import { useEStopStatus, useTriggerEStop, useResetEStop } from '@/hooks/useSecurity'
import { ChevronLeft, Shield, AlertTriangle, Loader2, RefreshCw, Power } from 'lucide-react'
import { cn } from '@/lib/utils'

interface SettingField {
  key: string
  label: string
  description: string
  type: 'number' | 'text' | 'boolean'
}

const SAFETY_GROUP: SettingField[] = [
  {
    key: 'security_pii_scrubber_enabled',
    label: 'PII Scrubber',
    description: 'Scan and block personal information (SSN, Email, CC) in agent turns.',
    type: 'boolean',
  },
  {
    key: 'security_prompt_injection_threshold',
    label: 'Injection Threshold',
    description: 'Risk score (0-1) above which prompts are blocked as injections.',
    type: 'number',
  },
]

const BUDGET_GROUP: SettingField[] = [
  {
    key: 'security_default_monthly_usd_cap',
    label: 'Default USD Cap',
    description: 'Default monthly budget cap for new users in USD.',
    type: 'number',
  },
]

const AUDIT_GROUP: SettingField[] = [
  {
    key: 'security_audit_retention_days',
    label: 'Audit Retention',
    description: 'Number of days to keep audit logs before rotation.',
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
    }
    if (parsed !== value) {
      onChange(field.key, parsed)
    }
  }

  const toggleBoolean = () => {
    const newVal = !value
    onChange(field.key, newVal)
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
        {field.type === 'boolean' ? (
          <button
            onClick={toggleBoolean}
            disabled={saving}
            className={cn(
              'relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none',
              value ? 'bg-accent-cyan' : 'bg-bg-elevated'
            )}
          >
            <span
              className={cn(
                'pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out',
                value ? 'translate-x-4' : 'translate-x-0'
              )}
            />
          </button>
        ) : field.type === 'number' ? (
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

export function SecuritySettingsPage() {
  const { data: settings = [], isLoading } = useSettings('security')
  const updateSetting = useUpdateSetting()
  const [savingKey, setSavingKey] = useState<string | null>(null)

  const { data: estopStatus } = useEStopStatus()
  const triggerEStop = useTriggerEStop()
  const resetEStop = useResetEStop()
  const [isConfirmingEStop, setIsConfirmingEStop] = useState(false)

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

  const handleEStop = () => {
    if (estopStatus?.active) {
      resetEStop.mutate()
    } else {
      setIsConfirmingEStop(true)
    }
  }

  const confirmEStop = () => {
    triggerEStop.mutate()
    setIsConfirmingEStop(false)
  }

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
            <div className="w-10 h-10 rounded-xl bg-accent-red/10 border border-accent-red/20 flex items-center justify-center text-accent-red">
              <Shield className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-sm font-display font-bold text-text-primary uppercase tracking-wider">
                Security Settings
              </h1>
              <p className="text-[10px] text-text-muted font-mono-data">
                Content safety, access control, and emergency overrides
              </p>
            </div>
          </div>
        </div>

        <div className="space-y-6">
          {/* E-Stop Block */}
          <div className={cn(
            "border rounded-xl p-5 transition-all",
            estopStatus?.active 
              ? "bg-accent-red/5 border-accent-red/30 shadow-glow-red/5" 
              : "bg-bg-surface border-border-dim"
          )}>
            <div className="flex items-center justify-between gap-4 mb-4">
              <div className="flex items-center gap-3">
                <div className={cn(
                  "w-8 h-8 rounded-lg flex items-center justify-center",
                  estopStatus?.active ? "bg-accent-red/20 text-accent-red" : "bg-bg-elevated text-text-muted"
                )}>
                  <Power className="w-4 h-4" />
                </div>
                <div>
                  <h2 className="text-xs font-display font-bold uppercase tracking-widest text-text-primary">
                    Emergency Stop
                  </h2>
                  <p className="text-[10px] text-text-muted mt-0.5">
                    {estopStatus?.active 
                      ? "System is currently locked. No agents can perform actions." 
                      : "Pause all agent activity and task execution immediately."}
                  </p>
                </div>
              </div>
              <button
                onClick={handleEStop}
                disabled={triggerEStop.isPending || resetEStop.isPending}
                className={cn(
                  "px-4 py-2 rounded-lg text-[11px] font-display font-bold uppercase tracking-wider transition-all",
                  estopStatus?.active
                    ? "bg-bg-elevated text-text-primary hover:bg-bg-surface border border-border-dim"
                    : "bg-accent-red text-white hover:bg-accent-red/90 shadow-lg shadow-accent-red/20"
                )}
              >
                {triggerEStop.isPending || resetEStop.isPending ? (
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                ) : estopStatus?.active ? (
                  "Reset System"
                ) : (
                  "Trigger E-Stop"
                )}
              </button>
            </div>
          </div>

          <SettingGroup
            title="Content Safety & PII"
            fields={SAFETY_GROUP}
            values={values}
            onChange={handleChange}
            savingKey={savingKey}
          />

          <SettingGroup
            title="Access & Budgets"
            fields={BUDGET_GROUP}
            values={values}
            onChange={handleChange}
            savingKey={savingKey}
          />

          <SettingGroup
            title="Audit & Compliance"
            fields={AUDIT_GROUP}
            values={values}
            onChange={handleChange}
            savingKey={savingKey}
          />
        </div>
      </div>

      {/* Confirmation Modal */}
      {isConfirmingEStop && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-bg-surface border border-border-dim rounded-2xl p-6 max-w-md w-full shadow-2xl animate-in fade-in zoom-in duration-200">
            <div className="flex items-center gap-3 text-accent-red mb-4">
              <AlertTriangle className="w-6 h-6" />
              <h3 className="text-lg font-display font-bold">Trigger Emergency Stop?</h3>
            </div>
            <p className="text-sm text-text-secondary mb-6 leading-relaxed">
              This will immediately halt all active agent tasks, skill invocations, and coordination across the entire system.
              Agents will be unable to process any input until the stop is manually reset.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setIsConfirmingEStop(false)}
                className="px-4 py-2 rounded-xl text-xs font-bold text-text-muted hover:bg-bg-elevated transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmEStop}
                className="px-4 py-2 rounded-xl text-xs font-bold bg-accent-red text-white hover:bg-accent-red/90 transition-all shadow-lg shadow-accent-red/20"
              >
                Trigger System Halt
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
