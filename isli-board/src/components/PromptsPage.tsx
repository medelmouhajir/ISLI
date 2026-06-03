import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { usePrompts, useUpdatePrompts } from '@/hooks/usePrompts'
import { FileText, RotateCcw, Save, AlertTriangle, Bot, Loader2, ChevronLeft, Code, LayoutTemplate } from 'lucide-react'
import { cn } from '@/lib/utils'
import yaml from 'js-yaml'
import type { PromptsOut, PromptsUpdate } from '@/types'

type TabKey = 'keeper' | 'agent' | 'core'

const TAB_CONFIG: { key: TabKey; label: string }[] = [
  { key: 'keeper', label: 'Keeper' },
  { key: 'agent', label: 'Agent' },
  { key: 'core', label: 'Core' },
]

function deepClone<T>(obj: T): T {
  return JSON.parse(JSON.stringify(obj))
}

function isDirty(original: PromptsOut | undefined, edited: PromptsOut | undefined): boolean {
  if (!original || !edited) return false
  return JSON.stringify(original) !== JSON.stringify(edited)
}

export function PromptsPage() {
  const { data, isLoading, refetch } = usePrompts()
  const updatePrompts = useUpdatePrompts()

  const [activeTab, setActiveTab] = useState<TabKey>('keeper')
  const [edited, setEdited] = useState<PromptsOut | null>(null)
  const [rawMode, setRawMode] = useState<Record<TabKey, boolean>>({ keeper: false, agent: false, core: false })
  const [rawText, setRawText] = useState<Record<TabKey, string>>({ keeper: '', agent: '', core: '' })
  const [rawError, setRawError] = useState<string | null>(null)
  const [showConflictModal, setShowConflictModal] = useState(false)
  const [showKeeperWarning, setShowKeeperWarning] = useState(false)

  // Initialise edited state when data arrives
  useEffect(() => {
    if (data) {
      setEdited(deepClone(data))
    }
  }, [data])

  const dirty = useMemo(() => isDirty(data ?? undefined, edited ?? undefined), [data, edited])

  // ── Structured field handlers ──────────────────────────────────────

  const handleKeeperChange = useCallback((key: string, value: string) => {
    setEdited((prev) => {
      if (!prev) return prev
      const next = deepClone(prev)
      next.keeper[key] = value
      return next
    })
  }, [])

  const handleAgentTemplateChange = useCallback((value: string) => {
    setEdited((prev) => {
      if (!prev) return prev
      const next = deepClone(prev)
      next.agent.system_prompt_template = value
      return next
    })
  }, [])

  const handleToolDescriptionChange = useCallback((tool: string, value: string) => {
    setEdited((prev) => {
      if (!prev) return prev
      const next = deepClone(prev)
      next.agent.tool_descriptions[tool] = value
      return next
    })
  }, [])

  const handleCoreChange = useCallback((key: string, value: string | string[]) => {
    setEdited((prev) => {
      if (!prev) return prev
      const next = deepClone(prev)
      if (key === 'prompt_injection_markers' && Array.isArray(value)) {
        next.core.prompt_injection_markers = value
      } else if (typeof value === 'string') {
        ;(next.core as Record<string, string | string[]>)[key] = value
      }
      return next
    })
  }, [])

  // ── Raw mode helpers ───────────────────────────────────────────────

  const toggleRawMode = useCallback((tab: TabKey) => {
    setRawError(null)
    setRawMode((prev) => {
      const enteringRaw = !prev[tab]
      if (enteringRaw && edited) {
        // Structured → Raw: dump the current tab section
        const section = tab === 'keeper' ? edited.keeper : tab === 'agent' ? edited.agent : edited.core
        try {
          const dumped = yaml.dump(section, { sortKeys: false, noRefs: true, lineWidth: -1 })
          setRawText((rt) => ({ ...rt, [tab]: dumped }))
        } catch {
          setRawText((rt) => ({ ...rt, [tab]: JSON.stringify(section, null, 2) }))
        }
      }
      return { ...prev, [tab]: enteringRaw }
    })
  }, [edited])

  const handleRawTextChange = useCallback((tab: TabKey, text: string) => {
    setRawText((prev) => ({ ...prev, [tab]: text }))
    setRawError(null)
  }, [])

  const tryParseRaw = useCallback((tab: TabKey): boolean => {
    const text = rawText[tab]
    try {
      const parsed = yaml.load(text)
      if (parsed === undefined || parsed === null) {
        setRawError('Parsed content is empty.')
        return false
      }
      setEdited((prev) => {
        if (!prev) return prev
        const next = deepClone(prev)
        if (tab === 'keeper') next.keeper = parsed as PromptsOut['keeper']
        else if (tab === 'agent') next.agent = parsed as PromptsOut['agent']
        else next.core = parsed as PromptsOut['core']
        return next
      })
      return true
    } catch (err) {
      setRawError(err instanceof Error ? err.message : 'Invalid YAML')
      return false
    }
  }, [rawText])

  const exitRawMode = useCallback((tab: TabKey) => {
    if (tryParseRaw(tab)) {
      setRawMode((prev) => ({ ...prev, [tab]: false }))
      setRawError(null)
    }
  }, [tryParseRaw])

  // ── Save / Discard ─────────────────────────────────────────────────

  const handleSave = useCallback(() => {
    if (!edited || !data) return

    // If any tab is in raw mode, try to parse it first
    for (const tab of TAB_CONFIG.map((t) => t.key)) {
      if (rawMode[tab]) {
        if (!tryParseRaw(tab)) return
      }
    }

    const payload: PromptsUpdate = {
      keeper: edited.keeper,
      agent: edited.agent,
      core: edited.core,
      last_modified: data.last_modified,
    }

    updatePrompts.mutate(payload, {
      onSuccess: (result) => {
        if (!result.keeper_reloaded) {
          setShowKeeperWarning(true)
          setTimeout(() => setShowKeeperWarning(false), 8000)
        }
      },
      onError: (err: unknown) => {
        const msg = err instanceof Error ? err.message : ''
        if (msg.includes('409') || msg.includes('Conflict')) {
          setShowConflictModal(true)
        }
      },
    })
  }, [edited, data, rawMode, tryParseRaw, updatePrompts])

  const handleDiscard = useCallback(() => {
    if (data) {
      setEdited(deepClone(data))
      setRawText({ keeper: '', agent: '', core: '' })
      setRawError(null)
      setRawMode({ keeper: false, agent: false, core: false })
    }
  }, [data])

  if (isLoading || !data || !edited) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-base">
        <div className="w-12 h-12 border-4 border-accent-cyan/20 border-t-accent-cyan rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto bg-bg-base h-full w-full min-h-0">
      <div className="p-6 md:p-8 max-w-5xl mx-auto space-y-6">
        {/* ── Agent restart banner ── */}
        <div className="bg-accent-amber/5 border border-accent-amber/20 rounded-xl p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-accent-amber shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm text-text-primary">
              Agent runners load prompts at startup. Restart any running agent to apply changes.
            </p>
            <Link
              to="/agents"
              className="inline-flex items-center gap-1.5 mt-2 text-xs font-semibold text-accent-cyan hover:text-accent-cyan/80 transition-colors"
            >
              <Bot className="w-3.5 h-3.5" />
              Go to Agents
            </Link>
          </div>
        </div>

        {/* ── Header ── */}
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
              <FileText className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-sm font-display font-bold text-text-primary uppercase tracking-wider">
                Prompts
              </h1>
              <p className="text-[10px] text-text-muted font-mono-data">
                Edit system prompts for Keeper, agents, and Core. Changes write to prompts.yaml.
              </p>
            </div>
          </div>
        </div>

        {/* ── Keeper reload warning toast ── */}
        {showKeeperWarning && (
          <div className="bg-accent-amber/5 border border-accent-amber/20 rounded-xl p-4 flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-accent-amber shrink-0 mt-0.5" />
            <p className="text-sm text-text-primary">
              Saved to disk, but Keeper could not be notified. Changes may not take effect until Keeper restarts.
            </p>
          </div>
        )}

        {/* ── Tabs + Raw toggle ── */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1 bg-bg-surface border border-border-dim rounded-lg p-1">
            {TAB_CONFIG.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={cn(
                  'px-4 py-1.5 rounded-md text-xs font-display font-bold uppercase tracking-widest transition-all',
                  activeTab === tab.key
                    ? 'bg-accent-cyan/10 text-accent-cyan'
                    : 'text-text-muted hover:text-text-secondary'
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <button
            onClick={() => {
              if (rawMode[activeTab]) {
                exitRawMode(activeTab)
              } else {
                toggleRawMode(activeTab)
              }
            }}
            className={cn(
              'flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all',
              rawMode[activeTab]
                ? 'bg-accent-cyan/10 border-accent-cyan/30 text-accent-cyan'
                : 'bg-bg-surface border-border-dim text-text-muted hover:text-text-secondary hover:border-border-bright'
            )}
          >
            {rawMode[activeTab] ? <LayoutTemplate className="w-3.5 h-3.5" /> : <Code className="w-3.5 h-3.5" />}
            {rawMode[activeTab] ? 'Structured' : 'Raw YAML'}
          </button>
        </div>

        {/* ── Raw error ── */}
        {rawError && (
          <div className="bg-accent-red/5 border border-accent-red/20 rounded-xl p-4">
            <p className="text-sm text-accent-red font-mono-data">{rawError}</p>
          </div>
        )}

        {/* ── Tab content ── */}
        {rawMode[activeTab] ? (
          <RawEditor
            tab={activeTab}
            text={rawText[activeTab]}
            onChange={(text) => handleRawTextChange(activeTab, text)}
          />
        ) : (
          <StructuredEditor
            tab={activeTab}
            data={edited}
            onKeeperChange={handleKeeperChange}
            onAgentTemplateChange={handleAgentTemplateChange}
            onToolDescriptionChange={handleToolDescriptionChange}
            onCoreChange={handleCoreChange}
          />
        )}

        {/* ── Action bar ── */}
        <div className="flex items-center justify-end gap-3 pt-4 border-t border-border-dim">
          <button
            onClick={handleDiscard}
            disabled={!dirty || updatePrompts.isPending}
            className={cn(
              'flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold border transition-all',
              dirty
                ? 'bg-bg-surface border-border-dim text-text-secondary hover:border-border-bright hover:text-text-primary'
                : 'bg-bg-surface border-border-dim/50 text-text-muted cursor-not-allowed'
            )}
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Discard Changes
          </button>
          <button
            onClick={handleSave}
            disabled={!dirty || updatePrompts.isPending || !!rawError}
            className={cn(
              'flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all',
              dirty && !rawError
                ? 'bg-accent-cyan text-white hover:bg-accent-cyan/90'
                : 'bg-accent-cyan/30 text-white/50 cursor-not-allowed'
            )}
          >
            {updatePrompts.isPending ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Save className="w-3.5 h-3.5" />
            )}
            Save Changes
          </button>
        </div>
      </div>

      {/* ── 409 Conflict modal ── */}
      {showConflictModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-bg-surface border border-border-dim rounded-xl p-6 max-w-md w-full space-y-4">
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-6 h-6 text-accent-amber" />
              <h3 className="text-sm font-display font-bold text-text-primary">Conflict Detected</h3>
            </div>
            <p className="text-sm text-text-secondary">
              Prompts were modified by another process. Refresh to load the latest version.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowConflictModal(false)}
                className="px-4 py-2 rounded-lg text-xs font-semibold text-text-secondary hover:text-text-primary transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  setShowConflictModal(false)
                  refetch()
                }}
                className="px-4 py-2 rounded-lg text-xs font-semibold bg-accent-cyan text-white hover:bg-accent-cyan/90 transition-colors"
              >
                Refresh
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────

function RawEditor({
  tab,
  text,
  onChange,
}: {
  tab: TabKey
  text: string
  onChange: (text: string) => void
}) {
  return (
    <div className="bg-bg-surface border border-border-dim rounded-xl overflow-hidden">
      <div className="px-4 py-2 bg-bg-elevated border-b border-border-dim flex items-center justify-between">
        <span className="text-[10px] font-mono-data uppercase tracking-wider text-text-muted">
          {tab}.yaml
        </span>
      </div>
      <textarea
        className="w-full h-[60vh] bg-bg-surface p-4 font-mono text-sm text-text-primary resize-none focus:outline-none"
        value={text}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
      />
    </div>
  )
}

function StructuredEditor({
  tab,
  data,
  onKeeperChange,
  onAgentTemplateChange,
  onToolDescriptionChange,
  onCoreChange,
}: {
  tab: TabKey
  data: PromptsOut
  onKeeperChange: (key: string, value: string) => void
  onAgentTemplateChange: (value: string) => void
  onToolDescriptionChange: (tool: string, value: string) => void
  onCoreChange: (key: string, value: string | string[]) => void
}) {
  if (tab === 'keeper') {
    return (
      <div className="space-y-4">
        {Object.entries(data.keeper).map(([key, value]) => {
          if (typeof value !== 'string') return null
          return (
            <PromptCard
              key={key}
              label={key}
              value={value}
              onChange={(v) => onKeeperChange(key, v)}
            />
          )
        })}
      </div>
    )
  }

  if (tab === 'agent') {
    return (
      <div className="space-y-4">
        <PromptCard
          label="system_prompt_template"
          value={data.agent.system_prompt_template}
          onChange={onAgentTemplateChange}
        />
        <div className="bg-bg-surface border border-border-dim rounded-xl p-5">
          <h2 className="text-xs font-display font-bold uppercase tracking-widest text-text-primary mb-4">
            Tool Descriptions
          </h2>
          <div className="space-y-3">
            {Object.entries(data.agent.tool_descriptions).map(([tool, desc]) => (
              <div key={tool} className="space-y-1.5">
                <label className="text-[11px] font-mono-data font-semibold text-text-secondary">{tool}</label>
                <textarea
                  className="w-full h-20 bg-bg-base border border-border-dim rounded-lg px-3 py-2 text-sm text-text-primary font-mono resize-y focus:outline-none focus:border-accent-cyan/50 focus:ring-2 focus:ring-accent-cyan/10"
                  value={desc}
                  onChange={(e) => onToolDescriptionChange(tool, e.target.value)}
                  spellCheck={false}
                />
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  // core
  return (
    <div className="space-y-4">
      <PromptCard
        label="help_text"
        value={data.core.help_text}
        onChange={(v) => onCoreChange('help_text', v)}
      />
      <PromptCard
        label="context_inject_task_desc"
        value={data.core.context_inject_task_desc}
        onChange={(v) => onCoreChange('context_inject_task_desc', v)}
      />
      <div className="bg-bg-surface border border-border-dim rounded-xl p-5">
        <h2 className="text-xs font-display font-bold uppercase tracking-widest text-text-primary mb-2">
          prompt_injection_markers
        </h2>
        <p className="text-[11px] text-text-muted mb-3">
          One regex pattern per line. These are used to detect prompt-injection attempts.
        </p>
        <textarea
          className="w-full h-48 bg-bg-base border border-border-dim rounded-lg px-3 py-2 text-sm text-text-primary font-mono resize-y focus:outline-none focus:border-accent-cyan/50 focus:ring-2 focus:ring-accent-cyan/10"
          value={data.core.prompt_injection_markers.join('\n')}
          onChange={(e) =>
            onCoreChange(
              'prompt_injection_markers',
              e.target.value.split('\n').map((l) => l.trim()).filter(Boolean)
            )
          }
          spellCheck={false}
        />
      </div>
    </div>
  )
}

function PromptCard({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <div className="bg-bg-surface border border-border-dim rounded-xl p-5 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-display font-bold uppercase tracking-widest text-text-primary">
          {label}
        </h2>
      </div>
      <textarea
        className="w-full h-48 bg-bg-base border border-border-dim rounded-lg px-3 py-2 text-sm text-text-primary font-mono resize-y focus:outline-none focus:border-accent-cyan/50 focus:ring-2 focus:ring-accent-cyan/10"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
      />
    </div>
  )
}
