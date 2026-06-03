import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getJSON, postJSON, deleteJSON } from '@/lib/api'
import type { NotificationListResponse } from '@/types'

export function useNotifications(filterStatus: 'all' | 'unread' | 'read' = 'all', eventType?: string) {
  return useQuery<NotificationListResponse>({
    queryKey: ['notifications', filterStatus, eventType],
    queryFn: () => {
      let url = `/v1/notifications?filter_status=${filterStatus}`
      if (eventType) url += `&event_type=${encodeURIComponent(eventType)}`
      return getJSON(url)
    },
    staleTime: 10000,
  })
}

export function useDigestNotifications(filterStatus: 'all' | 'unread' | 'read' = 'all') {
  return useNotifications(filterStatus, 'system:digest')
}

export function useUnreadCount() {
  return useQuery<{ unread_count: number }>({
    queryKey: ['notifications', 'unread-count'],
    queryFn: () => getJSON('/v1/notifications/unread-count'),
    staleTime: 5000,
    refetchInterval: 30000,
  })
}

export function useMarkRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => postJSON(`/v1/notifications/${id}/read`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
      queryClient.invalidateQueries({ queryKey: ['notifications', 'unread-count'] })
    },
  })
}

export function useMarkAllRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => postJSON('/v1/notifications/read-all', {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
      queryClient.invalidateQueries({ queryKey: ['notifications', 'unread-count'] })
    },
  })
}

export function useDismissNotification() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteJSON(`/v1/notifications/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
      queryClient.invalidateQueries({ queryKey: ['notifications', 'unread-count'] })
    },
  })
}
