import { ArrowUpCircle, GitCommit, ShieldCheck } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { SkillMetadata } from '@/types'

interface SkillVersionBadgeProps {
  skill: SkillMetadata
  onClick?: () => void
}

export function SkillVersionBadge({ skill, onClick }: SkillVersionBadgeProps) {
  const hasUpdate = skill.latest_version != null && skill.latest_version !== skill.version

  if (hasUpdate) {
    return (
      <button
        onClick={onClick}
        className={cn(
          'flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider',
          'bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/20',
          'hover:bg-accent-cyan/20 transition-colors cursor-pointer'
        )}
      >
        <ArrowUpCircle className="w-3 h-3" />
        {skill.version} → {skill.latest_version}
      </button>
    )
  }

  return (
    <div className="flex items-center gap-1 text-[10px] text-text-muted font-mono-data">
      <GitCommit className="w-3 h-3" />
      {skill.version || 'unknown'}
      {skill.update_policy === 'pinned' && (
        <span title="Pinned">
          <ShieldCheck className="w-3 h-3 ml-1 text-accent-amber" />
        </span>
      )}
    </div>
  )
}
