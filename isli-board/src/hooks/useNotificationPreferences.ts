import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getJSON, patchJSON } from '@/lib/api'
import type { NotificationPreferences } from '@/types'

export function useNotificationPreferences(userId: string) {
  return useQuery<NotificationPreferences>({
    queryKey: ['notification-preferences', userId],
    queryFn: () => getJSON(`/v1/notifications/preferences?user_id=${userId}`),
    staleTime: 60000,
  })
}

export function useUpdateNotificationPreferences(userId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: Partial<NotificationPreferences>) =>
      patchJSON(`/v1/notifications/preferences?user_id=${userId}`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notification-preferences', userId] })
    },
  })
}
