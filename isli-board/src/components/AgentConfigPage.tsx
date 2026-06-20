import { useState, useEffect, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useAgents, useUpdateAgent } from '@/hooks/useAgents'
import { Button } from '@/components/ui/Button'
import { Textarea } from '@/components/ui/Textarea'
import { Label } from '@/components/ui/Label'
import { ChevronLeft, FileJson, ShieldAlert } from 'lucide-react'
import { cn } from '@/lib/utils'

export function AgentConfigPage() {
  const { id } = useParams<{ id: string }>()
  const { data: agents = [], isLoading: agentsLoading } = useAgents()
  const updateAgent = useUpdateAgent()

  const agent = useMemo(() => agents.find((a) => a.id === id), [agents, id])

  const [configText, setConfigText] = useState('{}')
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [synced, setSynced] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (agent && !synced) {
      setConfigText(JSON.stringify(agent.config || {}, null, 2))
      setJsonError(null)
      setSynced(true)
    }
  }, [agent, synced])

  const handleJsonChange = (val: string) => {
    setConfigText(val)
    try {
      if (val.trim() === '') {
        setJsonError(null)
      } else {
        JSON.parse(val)
        setJsonError(null)
      }
    } catch (e) {
      setJsonError(e instanceof Error ? e.message : 'Invalid JSON')
    }
  }

  const isDirty = useMemo(() => {
    if (!agent) return false
    try {
      const currentParsed = JSON.parse(configText || '{}')
      const original = agent.config || {}
      return JSON.stringify(currentParsed) !== JSON.stringify(original)
    } catch {
      return true
    }
  }, [configText, agent])

  const handleSave = () => {
    if (!agent) return
    try {
      const parsedConfig = JSON.parse(configText || '{}')
      setJsonError(null)
      setSaving(true)
      updateAgent.mutate(
        { id: agent.id, payload: { config: parsedConfig } },
        {
          onSettled: () => {
            setSaving(false)
            setSynced(false) // Trigger re-sync from updated agent
          },
        }
      )
    } catch (e) {
      setJsonError(e instanceof Error ? e.message : 'Invalid JSON')
    }
  }

  const handleDiscard = () => {
    setSynced(false)
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
      <div className="flex-1 flex flex-col items-center justify-center bg-bg-base p-8 font-mono">
        <ShieldAlert className="w-16 h-16 text-accent-red mb-4" />
        <h1 className="text-2xl font-display font-bold text-text-primary">Agent Not Found</h1>
        <p className="text-text-secondary mt-2 mb-8 uppercase tracking-widest text-xs">
          The agent you are looking for does not exist or has been deleted.
        </p>
        <Link to="/agents">
          <Button className="rounded-none font-bold text-xs tracking-widest">
            Back to Agents
          </Button>
        </Link>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto bg-bg-base font-mono">
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
                <FileJson className="w-8 h-8 text-accent-cyan" />
                Raw Configuration
              </h1>
              <p className="text-text-secondary text-sm uppercase tracking-widest">
                Read and modify the internal state dictionary
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            {isDirty && (
              <Button
                variant="ghost"
                onClick={handleDiscard}
                disabled={saving}
                className="text-text-muted hover:text-text-primary rounded-none px-6 text-xs font-bold tracking-widest"
              >
                DISCARD
              </Button>
            )}
            <Button
              type="button"
              onClick={handleSave}
              disabled={saving || !isDirty || !!jsonError}
              className="bg-accent-cyan text-black hover:opacity-90 rounded-none px-8 font-bold text-xs tracking-widest disabled:opacity-50"
            >
              {saving ? 'SYNCING...' : 'SAVE_CHANGES'}
            </Button>
          </div>
        </div>

        {/* JSON Editor Container */}
        <div className="space-y-6">
          <div className="p-8 border border-border-bright bg-bg-surface space-y-6">
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <Label className="text-[10px] tracking-widest text-text-muted uppercase">
                  Internal State (JSON)
                </Label>
                {jsonError && (
                  <span className="text-[10px] text-accent-red font-bold tracking-widest uppercase animate-pulse">
                    PARSING_ERROR: {jsonError}
                  </span>
                )}
              </div>
              <Textarea
                value={configText}
                onChange={(e) => handleJsonChange(e.target.value)}
                rows={22}
                className={cn(
                  "bg-bg-base border-border-bright focus:border-accent-cyan text-text-secondary rounded-none resize-none font-mono text-[11px] leading-relaxed p-6 focus:ring-0 focus:outline-none transition-all",
                  jsonError && "border-accent-red focus:border-accent-red"
                )}
                placeholder={'{\n  "key": "value"\n}'}
              />
            </div>

            <div className="p-4 bg-bg-elevated/30 border border-border-dim text-[11px] text-text-secondary leading-relaxed uppercase space-y-2">
              <p className="font-bold text-text-primary">Configuration Guidelines:</p>
              <ul className="list-disc pl-4 space-y-1 text-text-muted">
                <li>Direct updates bypass UI validation restrictions. Ensure structure compatibility.</li>
                <li>Verify provider models, system tools parameters, and environment overrides.</li>
                <li>Invalid JSON will block synchronization updates.</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
