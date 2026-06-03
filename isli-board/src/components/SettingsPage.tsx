import { Link } from 'react-router-dom'
import { Zap, SlidersHorizontal, Shield, Bell, Brain, FileText, Palette } from 'lucide-react'
import { cn } from '@/lib/utils'

const categories = [
  {
    title: 'Model API Keys',
    description: 'Manage LLM provider API keys and permitted models for agent inference.',
    icon: Zap,
    path: '/settings/providers',
    active: true,
  },
  {
    title: 'Keeper Settings',
    description: 'Manage local Ollama models for the Keeper — pull and switch gen/embed models.',
    icon: Brain,
    path: '/settings/keeper',
    active: true,
  },
  {
    title: 'Appearance',
    description: 'Customize the visual theme, color palette, and dashboard style.',
    icon: Palette,
    path: '/settings/appearance',
    active: true,
  },
  {
    title: 'General',
    description: 'Global application preferences and defaults.',
    icon: SlidersHorizontal,
    path: '/settings/general',
    active: true,
  },
  {
    title: 'Prompts',
    description: 'Edit system prompts for Keeper, agents, and Core. Changes write to prompts.yaml.',
    icon: FileText,
    path: '/settings/prompts',
    active: true,
  },
  {
    title: 'Security',
    description: 'Authentication, access control, and audit settings.',
    icon: Shield,
    path: '#',
    active: false,
  },
  {
    title: 'Notifications',
    description: 'Alert routing, quiet hours, and communication preferences.',
    icon: Bell,
    path: '/settings/notifications',
    active: true,
  },
]

export function SettingsPage() {
  return (
    <div className="flex-1 overflow-y-auto bg-bg-base h-full w-full min-h-0">
      <div className="p-6 md:p-8 max-w-7xl mx-auto">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-accent-cyan/10 border border-accent-cyan/20 flex items-center justify-center text-accent-cyan">
            <SlidersHorizontal className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-sm font-display font-bold text-text-primary uppercase tracking-wider">
              Settings
            </h1>
            <p className="text-[10px] text-text-muted font-mono-data">
              Manage global configuration and provider settings
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {categories.map((cat) => {
            const cardContent = (
              <div
                className={cn(
                  'bg-bg-surface border border-border-dim rounded-xl p-5 shadow-card transition-all',
                  cat.active
                    ? 'hover:border-accent-cyan/30 hover:shadow-glow-cyan/5 cursor-pointer'
                    : 'opacity-50 cursor-not-allowed'
                )}
              >
                <div className="flex items-center gap-3 mb-4">
                  <div
                    className={cn(
                      'w-9 h-9 rounded-lg flex items-center justify-center',
                      cat.active ? 'bg-accent-cyan/10 text-accent-cyan' : 'bg-bg-elevated text-text-muted'
                    )}
                  >
                    <cat.icon className="w-4 h-4" />
                  </div>
                  <h2 className="text-xs font-display font-bold uppercase tracking-widest text-text-primary">
                    {cat.title}
                  </h2>
                  {!cat.active && (
                    <span className="ml-auto text-[9px] font-mono-data uppercase tracking-wider text-text-muted bg-bg-elevated px-2 py-0.5 rounded">
                      Soon
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-text-secondary leading-relaxed">
                  {cat.description}
                </p>
              </div>
            )

            return cat.active ? (
              <Link key={cat.title} to={cat.path} className="block">
                {cardContent}
              </Link>
            ) : (
              <div key={cat.title} className="block">
                {cardContent}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
