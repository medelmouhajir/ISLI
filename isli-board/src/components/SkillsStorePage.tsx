import { useState, useEffect, useCallback } from 'react'
import { ShoppingBag, Download, Search, ExternalLink, CheckCircle2, AlertCircle, Loader2, Trash2, RefreshCw, Play, Square, ArrowUpCircle, RefreshCcw } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/Button'
import { ConfirmationModal } from '@/components/ui/ConfirmationModal'
import { postJSON, getJSON, deleteJSON } from '@/lib/api'
import type { SkillMetadata } from '@/types'
import { SkillUpdateModal } from './SkillUpdateModal'
import { SkillVersionBadge } from './SkillVersionBadge'

interface RegistrySkill {
  id: string
  name: string
  description: string
  author: string
  git_url: string
  tags: string[]
}

const REGISTRY_URL = 'https://raw.githubusercontent.com/medelmouhajir/isli-skills-registry/main/index.json'

export function SkillsStorePage() {
  const [registrySkills, setRegistrySkills] = useState<RegistrySkill[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [installingId, setInstallingId] = useState<string | null>(null)
  const [togglingId, setTogglingId] = useState<string | null>(null)
  const [installedMap, setInstalledMap] = useState<Map<string, SkillMetadata>>(new Map())
  const [modalSkill, setModalSkill] = useState<SkillMetadata | null>(null)
  const [checkingAll, setCheckingAll] = useState(false)
  const [confirmModal, setConfirmModal] = useState<{
    open: boolean;
    title: string;
    description: string;
    confirmText?: string;
    onConfirm: () => void | Promise<void>;
    variant?: 'danger' | 'warning' | 'primary';
    hideCancel?: boolean;
  }>({
    open: false,
    title: '',
    description: '',
    onConfirm: () => {},
  })

  useEffect(() => {
    fetchRegistry()
    fetchInstalledSkills()
  }, [])

  const fetchInstalledSkills = async () => {
    try {
      const allSkills = await getJSON<SkillMetadata[]>('/v1/skills')
      const map = new Map<string, SkillMetadata>()
      for (const s of allSkills) {
        if (s.status && s.status !== 'builtin') {
          map.set(s.name, s)
        }
      }
      setInstalledMap(map)
    } catch (err) {
      console.error('Failed to fetch installed skills:', err)
    }
  }

  const pollSkillStatus = useCallback(async (skillId: string, maxAttempts = 20) => {
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      await new Promise(r => setTimeout(r, 3000))
      try {
        const skill = await getJSON<SkillMetadata>(`/v1/skills/${skillId}`)
        setInstalledMap(prev => {
          const next = new Map(prev)
          next.set(skillId, skill)
          return next
        })
        if (skill.status === 'active' && skill.last_probe_status === 'healthy') {
          return true
        }
        if (skill.status === 'error' || skill.last_probe_status === 'error') {
          return false
        }
      } catch (err) {
        console.error(`Poll attempt ${attempt + 1} failed for ${skillId}:`, err)
      }
    }
    return false
  }, [])

  const handleCheckAll = async () => {
    setCheckingAll(true)
    try {
      for (const [skillId] of installedMap) {
        try {
          await postJSON(`/v1/skills/${skillId}/check-update`, {})
          await pollSkillStatus(skillId, 1)
        } catch (err) {
          console.warn(`Check update failed for ${skillId}:`, err)
        }
      }
      await fetchInstalledSkills()
    } finally {
      setCheckingAll(false)
    }
  }

  const fetchRegistry = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const response = await fetch(REGISTRY_URL)
      if (!response.ok) throw new Error('Failed to fetch registry from GitHub')
      const data = await response.json()
      setRegistrySkills(data)
    } catch (err) {
      console.error('Registry fetch error:', err)
      setError('Could not load the skills registry. Please check your internet connection or try again later.')
      // Fallback for development/demo
      setRegistrySkills([
        {
          id: 'web-search-pro',
          name: 'Web Search Pro',
          description: 'Advanced web searching using SearxNG and Google.',
          author: 'ISLI-Team',
          git_url: 'https://github.com/isli-ai/skill-web-search',
          tags: ['utility', 'web']
        },
        {
          id: 'calculator',
          name: 'Calculator',
          description: 'Perform mathematical calculations.',
          author: 'ISLI-Team',
          git_url: 'https://github.com/isli-ai/skill-calculator',
          tags: ['utility', 'math']
        }
      ])
    } finally {
      setIsLoading(false)
    }
  }

  const handleInstall = async (skill: RegistrySkill) => {
    setInstallingId(skill.id)
    try {
      await postJSON('/v1/skills/install-and-enable', {
        skill_id: skill.id,
        git_url: skill.git_url
      })
      // Start polling for status updates
      await pollSkillStatus(skill.id)
    } catch (err: any) {
      console.error('Installation failed:', err)
      const detail = err?.message || 'Unknown error'
      setConfirmModal({
        open: true,
        title: 'Installation Failed',
        description: `Failed to install ${skill.name}: ${detail}`,
        onConfirm: () => {},
        hideCancel: true,
        variant: 'danger'
      })
      // Refresh to capture error status
      await fetchInstalledSkills()
    } finally {
      setInstallingId(null)
    }
  }

  const handleUninstall = async (skillId: string) => {
    setConfirmModal({
      open: true,
      title: 'Uninstall Skill',
      description: `Are you sure you want to uninstall ${skillId}?`,
      variant: 'danger',
      confirmText: 'Uninstall',
      onConfirm: async () => {
        try {
          await deleteJSON(`/v1/skills/${skillId}`)
          setInstalledMap(prev => {
            const next = new Map(prev)
            next.delete(skillId)
            return next
          })
        } catch (err) {
          console.error('Uninstall failed:', err)
          setConfirmModal({
            open: true,
            title: 'Uninstall Failed',
            description: `Failed to uninstall ${skillId}. See console for details.`,
            onConfirm: () => {},
            hideCancel: true,
            variant: 'danger'
          })
        }
      }
    })
  }

  const handleRetryEnable = async (skillId: string) => {
    setInstallingId(skillId)
    try {
      await postJSON(`/v1/skills/${skillId}/enable`, {})
      await pollSkillStatus(skillId)
    } catch (err: any) {
      console.error('Retry enable failed:', err)
      setConfirmModal({
        open: true,
        title: 'Operation Failed',
        description: `Failed to enable ${skillId}: ${err?.message || 'Unknown error'}`,
        onConfirm: () => {},
        hideCancel: true,
        variant: 'danger'
      })
      await fetchInstalledSkills()
    } finally {
      setInstallingId(null)
    }
  }

  const handleToggleSkill = async (skillId: string, action: 'enable' | 'disable') => {
    setTogglingId(skillId)
    try {
      await postJSON(`/v1/skills/${skillId}/${action}`, {})
      if (action === 'enable') {
        await pollSkillStatus(skillId)
      } else {
        await fetchInstalledSkills()
      }
    } catch (err: any) {
      console.error(`Toggle ${action} failed:`, err)
      setConfirmModal({
        open: true,
        title: 'Operation Failed',
        description: `Failed to ${action} ${skillId}: ${err?.message || 'Unknown error'}`,
        onConfirm: () => {},
        hideCancel: true,
        variant: 'danger'
      })
      await fetchInstalledSkills()
    } finally {
      setTogglingId(null)
    }
  }

  const getSkillStatus = (skillId: string): { label: string; color: string; icon: React.ReactNode } => {
    const meta = installedMap.get(skillId)
    if (!meta) return { label: '', color: '', icon: null }

    if (meta.status === 'pending') {
      return { label: 'Pending', color: 'text-accent-amber', icon: <Loader2 className="w-3 h-3 animate-spin" /> }
    }
    if (meta.last_probe_status === 'building') {
      return { label: 'Building', color: 'text-accent-amber', icon: <Loader2 className="w-3 h-3 animate-spin" /> }
    }
    if (meta.status === 'active' && meta.last_probe_status === 'healthy') {
      return { label: 'Running', color: 'text-accent-green', icon: <CheckCircle2 className="w-3 h-3" /> }
    }
    if (meta.status === 'active' && meta.last_probe_status === 'unhealthy') {
      return { label: 'Unhealthy', color: 'text-accent-red', icon: <AlertCircle className="w-3 h-3" /> }
    }
    if (meta.status === 'error' || meta.last_probe_status === 'error') {
      return { label: 'Build Failed', color: 'text-accent-red', icon: <AlertCircle className="w-3 h-3" /> }
    }
    if (meta.status === 'disabled') {
      return { label: 'Stopped', color: 'text-text-muted', icon: <AlertCircle className="w-3 h-3" /> }
    }
    return { label: meta.status || 'Unknown', color: 'text-text-muted', icon: null }
  }

  const filteredSkills = registrySkills.filter(s =>
    s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    s.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
    s.tags.some(t => t.toLowerCase().includes(searchQuery.toLowerCase()))
  )

  if (isLoading && registrySkills.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-base">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-accent-cyan/20 border-t-accent-cyan rounded-full animate-spin" />
          <span className="text-sm font-display font-medium text-text-muted">Fetching Registry...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto bg-bg-base p-6 md:p-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-display font-bold text-text-primary flex items-center gap-3">
            <ShoppingBag className="w-8 h-8 text-accent-pink" />
            Skills Store
          </h1>
          <p className="text-text-secondary mt-1 max-w-xl">
            Discover and install new capabilities for your agents from the community registry.
          </p>
        </div>
        <div className="flex flex-col md:flex-row gap-3 w-full md:w-auto">
          <Button
            variant="secondary"
            size="sm"
            onClick={handleCheckAll}
            disabled={checkingAll || installedMap.size === 0}
            className="text-xs"
          >
            {checkingAll ? (
              <><Loader2 className="w-3 h-3 mr-1.5 animate-spin" />Checking...</>
            ) : (
              <><RefreshCcw className="w-3 h-3 mr-1.5" />Check All for Updates</>
            )}
          </Button>
          <div className="relative w-full md:w-80">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
            <input
              type="text"
              placeholder="Search skills..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className={cn(
                "w-full bg-bg-surface border border-border-dim rounded-xl py-2 pl-10 pr-4",
                "text-sm text-text-primary placeholder:text-text-muted outline-none",
                "focus:border-accent-pink focus:shadow-glow-pink/10 transition-all"
              )}
            />
          </div>
        </div>
      </div>

      {error && (
        <div className="mb-8 p-4 bg-accent-red/10 border border-accent-red/20 rounded-xl flex items-center gap-3 text-accent-red text-sm">
          <AlertCircle className="w-5 h-5 shrink-0" />
          {error}
        </div>
      )}

      {/* Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {filteredSkills.map((skill) => {
          const isInstalled = installedMap.has(skill.id)
          const status = getSkillStatus(skill.id)
          const isBusy = installingId === skill.id || togglingId === skill.id

          return (
            <div
              key={skill.id}
              className={cn(
                'group flex flex-col p-5 rounded-2xl bg-bg-surface border border-border-dim',
                'hover:border-accent-pink hover:shadow-glow-pink/5 transition-all duration-300 relative overflow-hidden'
              )}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="w-12 h-12 rounded-xl bg-bg-elevated border border-border-dim flex items-center justify-center text-accent-pink group-hover:border-accent-pink/50 transition-colors">
                  <Download className="w-6 h-6" />
                </div>
                <div className="flex gap-1 flex-wrap justify-end">
                  {skill.tags.map(tag => (
                    <span key={tag} className="px-2 py-0.5 rounded-full bg-bg-elevated border border-border-dim text-[10px] text-text-muted uppercase font-mono-data">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>

              <div className="mb-6 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <h3 className="text-lg font-display font-bold text-text-primary group-hover:text-accent-pink transition-colors truncate">
                    {skill.name}
                  </h3>
                </div>
                <p className="text-[10px] text-text-muted font-mono-data mb-2">by {skill.author}</p>
                <p className="text-sm text-text-secondary line-clamp-3">
                  {skill.description}
                </p>
                {isInstalled && (
                  <div className="mt-2 flex items-center gap-2">
                    {status.label && (
                      <div className={cn("flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider", status.color)}>
                        {status.icon}
                        {status.label}
                      </div>
                    )}
                    {installedMap.get(skill.id) && (
                      <SkillVersionBadge
                        skill={installedMap.get(skill.id)!}
                        onClick={() => setModalSkill(installedMap.get(skill.id)!)}
                      />
                    )}
                  </div>
                )}
              </div>

              <div className="flex items-center gap-2 mt-auto">
                {isInstalled ? (
                  <>
                    {(installedMap.get(skill.id)?.status === 'error' || installedMap.get(skill.id)?.last_probe_status === 'error') ? (
                      <Button
                        onClick={() => handleRetryEnable(skill.id)}
                        disabled={isBusy}
                        className="w-full bg-accent-amber hover:bg-accent-amber/80"
                      >
                        {isBusy ? (
                          <>
                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                            Retrying...
                          </>
                        ) : (
                          <>
                            <RefreshCw className="w-4 h-4 mr-2" />
                            Retry Enable
                          </>
                        )}
                      </Button>
                    ) : installedMap.get(skill.id)?.status === 'disabled' ? (
                      <Button
                        onClick={() => handleToggleSkill(skill.id, 'enable')}
                        disabled={togglingId === skill.id}
                        className="w-full bg-accent-green hover:bg-accent-green/80"
                      >
                        {togglingId === skill.id ? (
                          <>
                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                            Starting...
                          </>
                        ) : (
                          <>
                            <Play className="w-4 h-4 mr-2" />
                            Start
                          </>
                        )}
                      </Button>
                    ) : installedMap.get(skill.id)?.status === 'active' && installedMap.get(skill.id)?.last_probe_status === 'healthy' ? (
                      <>
                        {(() => {
                          const meta = installedMap.get(skill.id)
                          const hasUpdate = meta?.latest_version != null && meta.latest_version !== meta.version
                          if (hasUpdate) {
                            return (
                              <Button
                                onClick={() => setModalSkill(meta!)}
                                disabled={isBusy}
                                className="w-full bg-accent-cyan hover:bg-accent-cyan/80 text-white"
                              >
                                <ArrowUpCircle className="w-4 h-4 mr-2" />
                                Update Available
                              </Button>
                            )
                          }
                          return (
                            <Button
                              onClick={() => handleToggleSkill(skill.id, 'disable')}
                              disabled={togglingId === skill.id}
                              variant="ghost"
                              className="w-full text-accent-amber bg-accent-amber/10 hover:bg-accent-amber/20"
                            >
                              {togglingId === skill.id ? (
                                <>
                                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                  Stopping...
                                </>
                              ) : (
                                <>
                                  <Square className="w-4 h-4 mr-2" />
                                  Stop
                                </>
                              )}
                            </Button>
                          )
                        })()}
                      </>
                    ) : (
                      <Button
                        variant="ghost"
                        className="w-full text-accent-green cursor-default bg-accent-green/10 hover:bg-accent-green/10"
                      >
                        <CheckCircle2 className="w-4 h-4 mr-2" />
                        Installed
                      </Button>
                    )}
                    <button
                      onClick={() => handleUninstall(skill.id)}
                      disabled={isBusy}
                      className="p-2 rounded-xl bg-bg-elevated border border-border-dim text-accent-red hover:bg-accent-red/10 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                      title="Uninstall"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </>
                ) : (
                  <Button
                    onClick={() => handleInstall(skill)}
                    disabled={isBusy}
                    className="w-full shadow-glow-pink"
                  >
                    {isBusy ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Installing...
                      </>
                    ) : (
                      <>
                        <Download className="w-4 h-4 mr-2" />
                        Install Skill
                      </>
                    )}
                  </Button>
                )}
                <a
                  href={skill.git_url}
                  target="_blank"
                  rel="noreferrer"
                  className="p-2 rounded-xl bg-bg-elevated border border-border-dim text-text-muted hover:text-text-primary hover:border-border-bright transition-all"
                  title="View Source"
                >
                  <ExternalLink className="w-4 h-4" />
                </a>
              </div>
            </div>
          )
        })}
      </div>

      {filteredSkills.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <ShoppingBag className="w-16 h-16 text-text-muted/20 mb-4" />
          <h3 className="text-xl font-display font-bold text-text-muted">No skills found</h3>
          <p className="text-text-muted mt-2">Try adjusting your search query.</p>
        </div>
      )}

      {modalSkill && (
        <SkillUpdateModal
          skill={modalSkill}
          onClose={() => setModalSkill(null)}
          onPoll={pollSkillStatus}
        />
      )}

      <ConfirmationModal
        open={confirmModal.open}
        title={confirmModal.title}
        description={confirmModal.description}
        variant={confirmModal.variant}
        confirmText={confirmModal.confirmText}
        hideCancel={confirmModal.hideCancel}
        onConfirm={confirmModal.onConfirm}
        onClose={() => setConfirmModal(prev => ({ ...prev, open: false }))}
      />
    </div>
  )
}
