import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getJSON, postJSON, deleteJSON } from '@/lib/api'
import type { Session } from '@/types'

export function useSessions(agentId?: string) {
  return useQuery<Session[]>({
    queryKey: ['sessions', agentId],
    queryFn: () => getJSON(`/v1/sessions${agentId ? `?agent_id=${agentId}` : ''}`),
    staleTime: 30000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
}

export function useSession(sessionId: string | null) {
  return useQuery<Session>({
    queryKey: ['sessions', sessionId],
    queryFn: () => {
      if (!sessionId) throw new Error('No session ID')
      return getJSON(`/v1/sessions/${sessionId}`)
    },
    enabled: !!sessionId,
    staleTime: 30000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
}

export function useCreateSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: { agent_id: string; user_id?: string; channel?: string }): Promise<Session> =>
      postJSON('/v1/sessions', payload),
    onSuccess: (newSession) => {
      // Optimistically update the sessions list
      queryClient.setQueryData(['sessions', undefined], (old: Session[] | undefined) => {
        if (!old) return [newSession]
        return [newSession, ...old]
      })
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })
}

export function useSendMessage() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ sessionId, text }: { sessionId: string; text: string }) =>
      postJSON(`/v1/sessions/${sessionId}/message`, { text }),
    onSuccess: (_, variables) => {
      // Only invalidate the detail query; WebSocket will update the list via setQueryData
      queryClient.invalidateQueries({ queryKey: ['sessions', variables.sessionId] })
    },
  })
}

export function useCloseSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (sessionId: string) =>
      postJSON(`/v1/sessions/${sessionId}/close`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })
}

export function useDeleteSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (sessionId: string) => deleteJSON(`/v1/sessions/${sessionId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })
}
