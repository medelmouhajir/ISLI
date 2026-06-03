import { useQuery } from '@tanstack/react-query'
import { getJSON } from '@/lib/api'
import type { CostByTier } from '@/types'

export function useCostByTier() {
  return useQuery({
    queryKey: ['cost-by-tier'],
    queryFn: () => getJSON<CostByTier[]>('/v1/system/cost/by-tier'),
    staleTime: 30000,
  })
}
