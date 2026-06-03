import { useQuery } from '@tanstack/react-query'
import { getJSON } from '@/lib/api'
import type { CostHistoryDay } from '@/types'

export function useCostHistory(days = 7) {
  return useQuery({
    queryKey: ['cost-history', days],
    queryFn: () => getJSON<CostHistoryDay[]>(`/v1/system/cost/history?days=${days}`),
    staleTime: 30000,
  })
}
