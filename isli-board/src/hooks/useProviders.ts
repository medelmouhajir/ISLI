import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getJSON, putJSON, postJSON, deleteJSON } from '@/lib/api'
import type { ProviderSettings, PermittedModel } from '@/types'

export function useProviders() {
  return useQuery({
    queryKey: ['providers'],
    queryFn: () => getJSON<ProviderSettings[]>('/v1/settings/providers'),
    staleTime: 30000,
  })
}

export function useUpdateProvider() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ provider, payload }: { provider: string; payload: Partial<ProviderSettings> }) =>
      putJSON<ProviderSettings>(`/v1/settings/providers/${provider}`, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['providers'] }),
  })
}

export function useAddPermittedModel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ provider, payload }: { provider: string; payload: { model_id: string; name?: string | null; enabled?: boolean } }) =>
      postJSON<PermittedModel>(`/v1/settings/providers/${provider}/models`, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['providers'] }),
  })
}

export function useRemovePermittedModel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ provider, modelId }: { provider: string; modelId: string }) =>
      deleteJSON(`/v1/settings/providers/${provider}/models/${modelId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['providers'] }),
  })
}
