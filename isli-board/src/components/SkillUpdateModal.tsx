import { useState } from 'react'
import { ArrowUpCircle, Loader2, RotateCcw, ShieldCheck, AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/Button'
import type { SkillMetadata } from '@/types'
import { useCheckSkillUpdate, useUpdateSkill, useRollbackSkill, usePatchSkill } from '@/hooks/useSkills'

interface SkillUpdateModalProps {
  skill: SkillMetadata
  onClose: () => void
  onPoll: (skillId: string) => Promise<boolean>
}

export function SkillUpdateModal({ skill, onClose, onPoll }: SkillUpdateModalProps) {
  const [checkError, setCheckError] = useState<string | null>(null)
  const [updateError, setUpdateError] = useState<string | null>(null)
  const [policy, setPolicy] = useState(skill.update_policy)

  const checkMutation = useCheckSkillUpdate(skill.name)
  const updateMutation = useUpdateSkill()
  const rollbackMutation = useRollbackSkill()
  const patchMutation = usePatchSkill()

  const hasUpdate = skill.latest_version != null && skill.latest_version !== skill.version

  const handleCheck = async () => {
    setCheckError(null)
    try {
      await checkMutation.mutateAsync()
      await onPoll(skill.name)
    } catch (err: any) {
      setCheckError(err?.message || 'Check failed')
    }
  }

  const handleUpdate = async () => {
    setUpdateError(null)
    try {
      await updateMutation.mutateAsync({ id: skill.name, payload: {} })
      await onPoll(skill.name)
    } catch (err: any) {
      setUpdateError(err?.message || 'Update failed')
    }
  }

  const handleRollback = async () => {
    setUpdateError(null)
    try {
      await rollbackMutation.mutateAsync(skill.name)
      await onPoll(skill.name)
    } catch (err: any) {
      setUpdateError(err?.message || 'Rollback failed')
    }
  }

  const handlePolicyChange = async (newPolicy: string) => {
    setPolicy(newPolicy)
    try {
      await patchMutation.mutateAsync({ id: skill.name, payload: { update_policy: newPolicy } })
      await onPoll(skill.name)
    } catch (err: any) {
      console.error('Failed to update policy:', err)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="w-full max-w-lg bg-bg-surface border border-border-dim rounded-2xl shadow-xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-border-dim flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ArrowUpCircle className={cn("w-5 h-5", hasUpdate ? "text-accent-cyan" : "text-text-muted")} />
            <h3 className="text-lg font-display font-bold text-text-primary">
              {skill.name} — Update
            </h3>
          </div>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary transition-colors">
            ✕
          </button>
        </div>

        <div className="px-6 py-5 space-y-5">
          {/* Version diff */}
          <div className="flex items-center gap-3 text-sm">
            <div className="flex-1 bg-bg-elevated rounded-lg px-3 py-2 border border-border-dim">
              <div className="text-text-muted text-[10px] uppercase tracking-wider mb-1">Current</div>
              <div className="font-mono-data text-text-primary">{skill.version || 'unknown'}</div>
              {skill.installed_commit_sha && (
                <div className="text-[10px] text-text-muted mt-0.5 truncate">{skill.installed_commit_sha.slice(0, 12)}</div>
              )}
            </div>
            <ArrowUpCircle className="w-5 h-5 text-text-muted shrink-0" />
            <div className={cn("flex-1 rounded-lg px-3 py-2 border", hasUpdate ? "bg-accent-cyan/10 border-accent-cyan/30" : "bg-bg-elevated border-border-dim")}>
              <div className="text-text-muted text-[10px] uppercase tracking-wider mb-1">Latest</div>
              <div className={cn("font-mono-data", hasUpdate ? "text-accent-cyan" : "text-text-primary")}>{skill.latest_version || '—'}</div>
              {skill.latest_commit_sha && (
                <div className="text-[10px] text-text-muted mt-0.5 truncate">{skill.latest_commit_sha.slice(0, 12)}</div>
              )}
            </div>
          </div>

          {/* Policy selector */}
          <div className="flex items-center gap-3">
            <ShieldCheck className="w-4 h-4 text-text-muted shrink-0" />
            <div className="flex-1">
              <label className="text-xs text-text-muted mb-1 block">Update Policy</label>
              <select
                value={policy}
                onChange={(e) => handlePolicyChange(e.target.value)}
                className="w-full bg-bg-elevated border border-border-dim rounded-lg px-3 py-2 text-sm text-text-primary outline-none focus:border-accent-cyan"
              >
                <option value="manual">Manual — notify only</option>
                <option value="auto">Auto — apply updates automatically</option>
                <option value="pinned">Pinned — never update</option>
              </select>
            </div>
          </div>

          {/* Changelog */}
          {skill.changelog && skill.changelog.length > 0 && (
            <div className="bg-bg-elevated rounded-lg border border-border-dim p-3">
              <div className="text-[10px] text-text-muted uppercase tracking-wider mb-2">Changelog</div>
              <div className="space-y-2 max-h-32 overflow-y-auto">
                {skill.changelog.slice(0, 5).map((entry, i) => (
                  <div key={i} className="text-xs">
                    <div className="flex items-center gap-2">
                      <span className="font-mono-data text-accent-cyan">{entry.version}</span>
                      <span className="text-text-muted">{entry.date}</span>
                    </div>
                    <p className="text-text-secondary mt-0.5 line-clamp-2">{entry.message}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Errors */}
          {checkError && (
            <div className="flex items-center gap-2 text-xs text-accent-amber">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              {checkError}
            </div>
          )}
          {updateError && (
            <div className="flex items-center gap-2 text-xs text-accent-red">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              {updateError}
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-2 pt-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={handleCheck}
              disabled={checkMutation.isPending}
              className="text-xs"
            >
              {checkMutation.isPending && <Loader2 className="w-3 h-3 mr-1 animate-spin" />}
              Check for Updates
            </Button>
            {hasUpdate && (
              <Button
                size="sm"
                onClick={handleUpdate}
                disabled={updateMutation.isPending}
                className="text-xs bg-accent-cyan hover:bg-accent-cyan/80"
              >
                {updateMutation.isPending && <Loader2 className="w-3 h-3 mr-1 animate-spin" />}
                Update Now
              </Button>
            )}
            {skill.previous_version && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleRollback}
                disabled={rollbackMutation.isPending}
                className="text-xs text-accent-amber hover:text-accent-amber"
              >
                {rollbackMutation.isPending && <Loader2 className="w-3 h-3 mr-1 animate-spin" />}
                <RotateCcw className="w-3 h-3 mr-1" />
                Rollback to {skill.previous_version}
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
