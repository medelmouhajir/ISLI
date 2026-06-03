import { useQuery } from '@tanstack/react-query'
import { getJSON } from '@/lib/api'
import type { BudgetStatus } from '@/types'

export function useBudgetStatus() {
  return useQuery({
    queryKey: ['budget-status'],
    queryFn: () => getJSON<BudgetStatus[]>('/v1/system/budgets'),
    staleTime: 30000,
  })
}
