import { useState, useMemo, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAgents, useUpdateAgent } from '@/hooks/useAgents'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { ConfirmationModal } from '@/components/ui/ConfirmationModal'
import { getJSON } from '@/lib/api'
import {
  ChevronLeft,
  Wrench,
  Check,
  Save,
  Shield,
  Search,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type { SkillMetadata } from '@/types'

export function AgentSkillsPage() {
  const { id } = useParams<{ id: string }>()
  const { data: agents = [] } = useAgents()
  const updateAgent = useUpdateAgent()

  const agent = useMemo(() => agents.find((a) => a.id === id), [agents, id])

  const { data: availableSkills = [], isLoading } = useQuery({
    queryKey: ['skills'],
    queryFn: () => getJSON<SkillMetadata[]>('/v1/skills'),
    staleTime: 30000,
  })

  const originalSkills = useMemo(() => [...(agent?.skills ?? [])], [agent])
  const [selected, setSelected] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
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

  // Sync selected with agent data when it loads
  const [synced, setSynced] = useState(false)
  if (agent && !synced) {
    setSelected([...agent.skills])
    setSynced(true)
  }
  if (!agent && synced) {
    setSynced(false)
  }

  const isDirty = useMemo(() => {
    if (selected.length !== originalSkills.length) return true
    const sortedSel = [...selected].sort()
    const sortedOrig = [...originalSkills].sort()
    return sortedSel.some((s, i) => s !== sortedOrig[i])
  }, [selected, originalSkills])

  const toggleSkill = useCallback((name: string) => {
    setSelected((prev) =>
      prev.includes(name) ? prev.filter((s) => s !== name) : [...prev, name]
    )
  }, [])

  const selectAllInCategory = useCallback((categorySkills: SkillMetadata[]) => {
    const skillNames = categorySkills.map(s => s.name)
    setSelected(prev => {
      const next = [...prev]
      skillNames.forEach(name => {
        if (!next.includes(name)) next.push(name)
      })
      return next
    })
  }, [])

  const unselectAllInCategory = useCallback((category: string, categorySkills: SkillMetadata[]) => {
    const skillNames = categorySkills.map(s => s.name)
    setConfirmModal({
      open: true,
      title: 'Disarm Skills',
      description: `Are you sure you want to unselect all skills in the "${category}" category?`,
      onConfirm: () => setSelected(prev => prev.filter(name => !skillNames.includes(name))),
    })
  }, [])

  const handleSave = () => {
    if (!agent) return
    setSaving(true)
    updateAgent.mutate(
      { id: agent.id, payload: { skills: selected } },
      { onSettled: () => setSaving(false) }
    )
  }

  const handleDiscard = () => {
    setSelected([...originalSkills])
  }

  // Filter and group skills by category
  const grouped = useMemo(() => {
    const map = new Map<string, SkillMetadata[]>()
    const query = searchQuery.toLowerCase().trim()

    const filtered = availableSkills.filter(skill => {
      if (!query) return true
      return (
        skill.name.toLowerCase().includes(query) ||
        (skill.description?.toLowerCase().includes(query)) ||
        (skill.category?.toLowerCase().includes(query))
      )
    })

    for (const skill of filtered) {
      const cat = skill.category || 'uncategorized'
      if (!map.has(cat)) map.set(cat, [])
      map.get(cat)!.push(skill)
    }
    return map
  }, [availableSkills, searchQuery])

  const sortedCategories = useMemo(
    () => [...grouped.keys()].sort(),
    [grouped]
  )

  if (!agent) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-bg-base p-8">
        <Shield className="w-16 h-16 text-accent-red mb-4" />
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
        <div className="flex flex-col gap-4">
          <Link
            to={`/agents/${id}`}
            className="flex items-center gap-2 text-xs font-display font-bold uppercase tracking-widest text-text-muted hover:text-accent-cyan transition-colors w-fit"
          >
            <ChevronLeft className="w-4 h-4" />
            Back to Agent
          </Link>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-none bg-bg-surface border border-border-dim flex items-center justify-center text-accent-cyan">
                <Wrench className="w-6 h-6" />
              </div>
              <div>
                <h1 className="text-xl font-display font-bold text-text-primary">Skill Arsenal</h1>
                <p className="text-[10px] font-mono-data text-text-muted uppercase tracking-wider">
                  Agent: {agent.name}
                  <span className="mx-2 text-border-dim">|</span>
                  {selected.length} of {availableSkills.length} armed
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Search */}
        <div className="relative group">
          <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted group-focus-within:text-accent-cyan transition-colors">
            <Search className="w-4 h-4" />
          </div>
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search arsenal by name, description, or category..."
            className="pl-10 pr-10"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-3.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Skills List */}
        <div className="bg-bg-surface border border-border-dim rounded-none overflow-hidden shadow-sm">
          <div className="px-6 py-4 border-b border-border-dim bg-bg-elevated/30 flex items-center justify-between">
            <h2 className="text-xs font-display font-bold uppercase tracking-widest text-text-secondary flex items-center gap-2">
              <Wrench className="w-4 h-4 text-accent-cyan" />
              Available Skills
            </h2>
            <span className="text-[10px] font-mono-data text-text-muted">
              {selected.length} selected
            </span>
          </div>

          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-6 h-6 border-2 border-accent-cyan/20 border-t-accent-cyan rounded-none animate-spin" />
            </div>
          ) : availableSkills.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 px-6">
              <Wrench className="w-12 h-12 text-text-muted mb-4 opacity-30" />
              <p className="text-sm text-text-secondary font-display">No skills registered</p>
              <p className="text-xs text-text-muted mt-1 text-center max-w-sm">
                Skills are registered in Core and discovered dynamically. Add skill microservices or inline handlers to populate this list.
              </p>
            </div>
          ) : sortedCategories.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 px-6">
              <Search className="w-12 h-12 text-text-muted mb-4 opacity-30" />
              <p className="text-sm text-text-secondary font-display">No matches found</p>
              <p className="text-xs text-text-muted mt-1 text-center max-w-sm">
                Adjust your search query to find the skills you are looking for.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-border-dim/50">
              {sortedCategories.map((category) => {
                const skills = grouped.get(category)!
                const allSelected = skills.every(s => selected.includes(s.name))
                const someSelected = skills.some(s => selected.includes(s.name))

                return (
                  <div key={category}>
                    <div className="px-6 py-2 bg-bg-elevated/20 border-b border-border-dim/30 flex items-center justify-between">
                      <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-text-muted/70">
                        {category}
                      </span>
                      <div className="flex items-center gap-4">
                        <button
                          type="button"
                          onClick={() => selectAllInCategory(skills)}
                          disabled={allSelected}
                          className={cn(
                            "text-[9px] font-bold uppercase tracking-tighter transition-colors",
                            allSelected ? "text-text-muted/30 cursor-not-allowed" : "text-accent-cyan hover:text-accent-cyan/80"
                          )}
                        >
                          Select All
                        </button>
                        <div className="w-px h-2 bg-border-dim/50" />
                        <button
                          type="button"
                          onClick={() => unselectAllInCategory(category, skills)}
                          disabled={!someSelected}
                          className={cn(
                            "text-[9px] font-bold uppercase tracking-tighter transition-colors",
                            !someSelected ? "text-text-muted/30 cursor-not-allowed" : "text-accent-red hover:text-accent-red/80"
                          )}
                        >
                          Clear All
                        </button>
                      </div>
                    </div>
                    {skills.map((skill) => {
                      const isSelected = selected.includes(skill.name)
                      return (
                        <button
                          key={skill.name}
                          type="button"
                          onClick={() => toggleSkill(skill.name)}
                          className={cn(
                            'w-full text-left px-6 py-4 flex items-start gap-4 transition-all duration-200',
                            isSelected
                              ? 'bg-accent-cyan/5 hover:bg-accent-cyan/10'
                              : 'hover:bg-bg-elevated/20'
                          )}
                        >
                          <div
                            className={cn(
                              'mt-0.5 w-5 h-5 rounded-none border flex items-center justify-center transition-colors shrink-0',
                              isSelected
                                ? 'bg-accent-cyan border-accent-cyan shadow-glow-cyan/20'
                                : 'border-border-dim'
                            )}
                          >
                            {isSelected && <Check className="w-3.5 h-3.5 text-white" />}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap mb-0.5">
                              <span
                                className={cn(
                                  'text-sm font-mono-data font-bold',
                                  isSelected ? 'text-accent-cyan' : 'text-text-primary'
                                )}
                              >
                                {skill.name}
                              </span>
                              <span
                                className={cn(
                                  'px-1.5 py-0.5 rounded-none text-[10px] font-bold uppercase tracking-wider border',
                                  skill.type === 'inline'
                                    ? 'bg-accent-amber/10 text-accent-amber border-accent-amber/20'
                                    : 'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/20'
                                )}
                              >
                                {skill.type}
                              </span>
                            </div>
                            {skill.description && (
                              <p className="text-xs text-text-muted leading-relaxed">
                                {skill.description}
                              </p>
                            )}
                            {skill.url && (
                              <p className="text-[10px] font-mono-data text-text-muted/50 mt-1">
                                {skill.url}
                              </p>
                            )}
                          </div>
                        </button>
                      )
                    })}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Sticky Action Footer */}
        {isDirty && (
          <div className="sticky bottom-0 z-10 bg-bg-base/80 backdrop-blur-sm border-t border-border-dim px-6 py-4 flex justify-end gap-3 animate-in fade-in slide-in-from-bottom-2 duration-200">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleDiscard}
              disabled={saving}
            >
              Discard
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={handleSave}
              disabled={saving}
              className="shadow-glow-cyan"
            >
              <Save className="w-3.5 h-3.5 mr-1.5" />
              {saving ? 'Saving...' : 'Save Changes'}
            </Button>
          </div>
        )}
      </div>
      <ConfirmationModal
        open={confirmModal.open}
        title={confirmModal.title}
        description={confirmModal.description}
        variant="warning"
        confirmText="Confirm"
        onConfirm={confirmModal.onConfirm}
        onClose={() => setConfirmModal(prev => ({ ...prev, open: false }))}
      />
    </div>
  )
}
