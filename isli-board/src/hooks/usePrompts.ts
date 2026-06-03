import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getJSON, putJSON } from '@/lib/api'
import type { PromptsOut, PromptsUpdate } from '@/types'

export function usePrompts() {
  return useQuery({
    queryKey: ['prompts'],
    queryFn: () => getJSON<PromptsOut>('/v1/prompts'),
    staleTime: 0,
  })
}

export function useUpdatePrompts() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: PromptsUpdate) =>
      putJSON<PromptsOut>('/v1/prompts', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prompts'] })
    },
  })
}
