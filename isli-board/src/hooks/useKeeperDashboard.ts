import { useQuery } from '@tanstack/react-query'
import { getJSON } from '@/lib/api'
import type { KeeperDashboard } from '@/types'

export function useKeeperDashboard() {
  return useQuery({
    queryKey: ['keeper-dashboard'],
    queryFn: () => getJSON<KeeperDashboard>('/v1/system/keeper/dashboard'),
    refetchInterval: 5000,
    staleTime: 4000,
  })
}
