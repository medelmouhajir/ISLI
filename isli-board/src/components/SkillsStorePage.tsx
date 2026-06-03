import { useState, useEffect } from 'react'
import { ShoppingBag, Download, Search, ExternalLink, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/Button'
import { postJSON } from '@/lib/api'

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
  const [skills, setSkills] = useState<RegistrySkill[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [installingId, setInstallingId] = useState<string | null>(null)
  const [installedIds, setInstalledIds] = useState<Set<string>>(new Set())

  useEffect(() => {
    fetchRegistry()
  }, [])

  const fetchRegistry = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const response = await fetch(REGISTRY_URL)
      if (!response.ok) throw new Error('Failed to fetch registry from GitHub')
      const data = await response.json()
      setSkills(data)
    } catch (err) {
      console.error('Registry fetch error:', err)
      setError('Could not load the skills registry. Please check your internet connection or try again later.')
      // Fallback for development/demo
      setSkills([
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
      await postJSON('/v1/skills/install', {
        skill_id: skill.id,
        git_url: skill.git_url
      })
      setInstalledIds(prev => new Set(prev).add(skill.id))
    } catch (err) {
      console.error('Installation failed:', err)
      alert(`Failed to install ${skill.name}. See console for details.`)
    } finally {
      setInstallingId(null)
    }
  }

  const filteredSkills = skills.filter(s => 
    s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    s.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
    s.tags.some(t => t.toLowerCase().includes(searchQuery.toLowerCase()))
  )

  if (isLoading && skills.length === 0) {
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

      {error && (
        <div className="mb-8 p-4 bg-accent-red/10 border border-accent-red/20 rounded-xl flex items-center gap-3 text-accent-red text-sm">
          <AlertCircle className="w-5 h-5 shrink-0" />
          {error}
        </div>
      )}

      {/* Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {filteredSkills.map((skill) => (
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
              <div className="flex gap-1">
                {skill.tags.map(tag => (
                  <span key={tag} className="px-2 py-0.5 rounded-full bg-bg-elevated border border-border-dim text-[10px] text-text-muted uppercase font-mono-data">
                    {tag}
                  </span>
                ))}
              </div>
            </div>

            <div className="mb-6 flex-1">
              <h3 className="text-lg font-display font-bold text-text-primary group-hover:text-accent-pink transition-colors truncate">
                {skill.name}
              </h3>
              <p className="text-[10px] text-text-muted font-mono-data mb-2">by {skill.author}</p>
              <p className="text-sm text-text-secondary line-clamp-3">
                {skill.description}
              </p>
            </div>

            <div className="flex items-center gap-2 mt-auto">
              {installedIds.has(skill.id) ? (
                <Button variant="ghost" className="w-full text-accent-green cursor-default bg-accent-green/10 hover:bg-accent-green/10">
                  <CheckCircle2 className="w-4 h-4 mr-2" />
                  Installed
                </Button>
              ) : (
                <Button 
                  onClick={() => handleInstall(skill)}
                  disabled={installingId === skill.id}
                  className="w-full shadow-glow-pink"
                >
                  {installingId === skill.id ? (
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
        ))}
      </div>

      {filteredSkills.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <ShoppingBag className="w-16 h-16 text-text-muted/20 mb-4" />
          <h3 className="text-xl font-display font-bold text-text-muted">No skills found</h3>
          <p className="text-text-muted mt-2">Try adjusting your search query.</p>
        </div>
      )}
    </div>
  )
}
