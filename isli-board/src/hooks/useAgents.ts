import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getJSON, putJSON, deleteJSON } from '@/lib/api'
import type { Agent } from '@/types'

export function useAgents() {
  return useQuery({
    queryKey: ['agents'],
    queryFn: () => getJSON<Agent[]>('/v1/agents'),
    staleTime: 30000,
  })
}

export function useUpdateAgent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<Agent> }) =>
      putJSON<Agent>(`/v1/agents/${id}`, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['agents'] }),
  })
}

export function useDeleteAgent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteJSON(`/v1/agents/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['agents'] }),
  })
}
