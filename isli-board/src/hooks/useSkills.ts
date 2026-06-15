import { useMutation, useQueryClient } from '@tanstack/react-query'
import { postJSON, patchJSON } from '@/lib/api'
import type { SkillMetadata } from '@/types'

export interface SkillUpdateCheckOut {
  has_update: boolean
  current_version: string | null
  latest_version: string | null
  current_commit: string | null
  latest_commit: string | null
  changelog: Array<{ version: string; date: string; message: string }>
  update_policy: string
  last_checked_at: string | null
}

export interface SkillUpdateRequest {
  target_version?: string | null
  force?: boolean
}

export interface SkillRollbackOut {
  skill_id: string
  rolled_back_to_version: string | null
  rolled_back_to_commit: string | null
  status: string
}

export function useCheckSkillUpdate(skillId: string) {
  return useMutation<SkillUpdateCheckOut, Error, void>({
    mutationFn: () => postJSON<SkillUpdateCheckOut>(`/v1/skills/${skillId}/check-update`, {}),
  })
}

export function useUpdateSkill() {
  const queryClient = useQueryClient()
  return useMutation<SkillMetadata, Error, { id: string; payload: SkillUpdateRequest }>({
    mutationFn: ({ id, payload }) => postJSON<SkillMetadata>(`/v1/skills/${id}/update`, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['skills'] }),
  })
}

export function useRollbackSkill() {
  const queryClient = useQueryClient()
  return useMutation<SkillRollbackOut, Error, string>({
    mutationFn: (id) => postJSON<SkillRollbackOut>(`/v1/skills/${id}/rollback`, {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['skills'] }),
  })
}

export function usePatchSkill() {
  const queryClient = useQueryClient()
  return useMutation<SkillMetadata, Error, { id: string; payload: { update_policy?: string; source_ref?: string } }>({
    mutationFn: ({ id, payload }) => patchJSON<SkillMetadata>(`/v1/skills/${id}`, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['skills'] }),
  })
}
