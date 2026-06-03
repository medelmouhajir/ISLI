import { Link } from 'react-router-dom'
import { ChevronLeft, Palette, Check } from 'lucide-react'
import { useTheme } from '@/hooks/useTheme'
import { cn } from '@/lib/utils'

interface ThemeOption {
  id: string
  name: string
  description: string
  colors: {
    base: string
    surface: string
    accent: string
  }
}

const THEMES: ThemeOption[] = [
  {
    id: 'system',
    name: 'System Default',
    description: 'Sync with your operating system appearance.',
    colors: { base: '#f1f5f9', surface: '#ffffff', accent: '#0ea5e9' },
  },
  {
    id: 'light',
    name: 'Light',
    description: 'Clean and bright interface for daytime use.',
    colors: { base: '#f8fafc', surface: '#ffffff', accent: '#0ea5e9' },
  },
  {
    id: 'dark',
    name: 'Dark',
    description: 'Classic high-contrast dark mode for low light.',
    colors: { base: '#050508', surface: '#0a0a12', accent: '#00f0ff' },
  },
  {
    id: 'midnight',
    name: 'Midnight',
    description: 'Deep navy surface with violet accents.',
    colors: { base: '#05070a', surface: '#0f1117', accent: '#7c6af7' },
  },
  {
    id: 'obsidian',
    name: 'Obsidian',
    description: 'Pure industrial black with teal highlights.',
    colors: { base: '#000000', surface: '#080808', accent: '#00ffcc' },
  },
  {
    id: 'dusk',
    name: 'Dusk',
    description: 'Deep plum tones with rose accents.',
    colors: { base: '#0f050a', surface: '#1a0f14', accent: '#ff3366' },
  },
  {
    id: 'terminal',
    name: 'Terminal',
    description: 'Void black with green phosphor text.',
    colors: { base: '#000000', surface: '#0a0a0a', accent: '#00ff41' },
  },
  {
    id: 'canvas',
    name: 'Canvas',
    description: 'Warm gallery white with indigo accents.',
    colors: { base: '#f5f5f5', surface: '#fcfbf9', accent: '#4f46e5' },
  },
  {
    id: 'sandstone',
    name: 'Sandstone',
    description: 'Natural desert tones with amber highlights.',
    colors: { base: '#dccfb8', surface: '#e8dcc7', accent: '#d97706' },
  },
]

export function AppearanceSettingsPage() {
  const { theme, setTheme } = useTheme()

  return (
    <div className="flex-1 overflow-y-auto bg-bg-base h-full w-full min-h-0">
      <div className="p-6 md:p-8 max-w-5xl mx-auto space-y-8">
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
              <Palette className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-sm font-display font-bold text-text-primary uppercase tracking-wider">
                Appearance
              </h1>
              <p className="text-[10px] text-text-muted font-mono-data">
                Customize the visual style and themes of the dashboard
              </p>
            </div>
          </div>
        </div>

        {/* Theme Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {THEMES.map((t) => (
            <button
              key={t.id}
              onClick={() => setTheme(t.id as any)}
              className={cn(
                'group relative flex flex-col items-start p-4 rounded-xl border transition-all text-left',
                theme === t.id
                  ? 'bg-bg-surface border-accent-cyan ring-1 ring-accent-cyan/50 shadow-glow-cyan/10'
                  : 'bg-bg-surface/50 border-border-dim hover:border-border-bright hover:bg-bg-surface'
              )}
            >
              {/* Theme Preview Tooltip-like preview */}
              <div className="w-full h-24 rounded-lg mb-4 overflow-hidden border border-border-dim/50 flex flex-col">
                <div style={{ backgroundColor: t.colors.base }} className="flex-1 p-2 flex gap-2">
                  <div style={{ backgroundColor: t.colors.surface }} className="w-1/3 rounded-md shadow-sm border border-border-dim/20" />
                  <div className="flex-1 space-y-2">
                    <div style={{ backgroundColor: t.colors.surface }} className="h-2 w-full rounded-full opacity-50" />
                    <div style={{ backgroundColor: t.colors.accent }} className="h-2 w-2/3 rounded-full" />
                    <div style={{ backgroundColor: t.colors.surface }} className="h-2 w-1/2 rounded-full opacity-50" />
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between w-full mb-1">
                <span className="text-xs font-display font-bold uppercase tracking-wider text-text-primary">
                  {t.name}
                </span>
                {theme === t.id && (
                  <Check className="w-3.5 h-3.5 text-accent-cyan" />
                )}
              </div>
              <p className="text-[10px] text-text-muted leading-relaxed">
                {t.description}
              </p>

              {/* Selection indicator */}
              {theme === t.id && (
                <div className="absolute top-0 right-0 w-8 h-8 flex items-center justify-center">
                  <div className="absolute top-0 right-0 w-0 h-0 border-t-[32px] border-l-[32px] border-t-accent-cyan border-l-transparent rounded-tr-xl opacity-10" />
                </div>
              )}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
