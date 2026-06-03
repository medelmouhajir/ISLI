import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getJSON, putJSON, deleteJSON } from '@/lib/api'
import type { SystemSetting } from '@/types'

export function useSettings(scope?: string) {
  const queryKey = scope ? ['settings', scope] : ['settings']
  const path = scope ? `/v1/settings?scope=${scope}` : '/v1/settings'
  return useQuery({
    queryKey,
    queryFn: () => getJSON<SystemSetting[]>(path),
    staleTime: 30000,
  })
}

export function useUpdateSetting() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: unknown }) =>
      putJSON<SystemSetting>(`/v1/settings/${key}`, { value }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['settings'] }),
  })
}

export function useDeleteSetting() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (key: string) => deleteJSON(`/v1/settings/${key}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['settings'] }),
  })
}
