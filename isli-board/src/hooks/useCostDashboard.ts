import { useQuery } from '@tanstack/react-query'
import { getJSON } from '@/lib/api'
import type { CostDashboard } from '@/types'

export function useCostDashboard() {
  return useQuery({
    queryKey: ['cost-dashboard'],
    queryFn: () => getJSON<CostDashboard>('/v1/system/cost/dashboard'),
    staleTime: 30000,
  })
}
