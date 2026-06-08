import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getJSON, postJSON } from '@/lib/api'

export interface EStopStatus {
  active: boolean
}

export function useEStopStatus() {
  return useQuery({
    queryKey: ['security', 'estop'],
    queryFn: () => getJSON<EStopStatus>('/v1/security/estop/status'),
    refetchInterval: 5000, // Poll every 5s for safety status
  })
}

export function useTriggerEStop() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => postJSON<EStopStatus>('/v1/security/estop/trigger', {}),
    onSuccess: (data) => {
      queryClient.setQueryData(['security', 'estop'], data)
    },
  })
}

export function useResetEStop() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => postJSON<EStopStatus>('/v1/security/estop/reset', {}),
    onSuccess: (data) => {
      queryClient.setQueryData(['security', 'estop'], data)
    },
  })
}
