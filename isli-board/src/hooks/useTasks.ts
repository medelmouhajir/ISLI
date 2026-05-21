import { useQuery } from '@tanstack/react-query'
import { getJSON } from '@/lib/api'
import type { Task } from '@/types'

export function useTasks() {
  return useQuery({
    queryKey: ['tasks'],
    queryFn: () => getJSON<Task[]>('/v1/tasks'),
    staleTime: 30000,
  })
}
