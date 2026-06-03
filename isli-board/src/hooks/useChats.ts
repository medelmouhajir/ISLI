import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getJSON, postJSON } from '@/lib/api'
import type { Session, SessionHistory } from '@/types'

export function useChatSessions(agentId?: string, channel?: string, includeClosed = true) {
  const params = new URLSearchParams()
  if (agentId) params.set('agent_id', agentId)
  if (channel) params.set('channel', channel)
  params.set('include_closed', String(includeClosed))
  params.set('limit', '200')

  return useQuery<Session[]>({
    queryKey: ['chat-sessions', agentId, channel],
    queryFn: () => getJSON(`/v1/sessions?${params.toString()}`),
    staleTime: 30000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    enabled: !!agentId && !!channel,
  })
}

export function useSessionHistory(sessionId: string | null) {
  return useQuery<SessionHistory>({
    queryKey: ['session-history', sessionId],
    queryFn: () => getJSON(`/v1/sessions/${sessionId}/history`),
    staleTime: 30000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    enabled: !!sessionId,
  })
}

export function useSendChatMessage() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ sessionId, text, voiceMode }: { sessionId: string; text: string; voiceMode?: boolean }) =>
      postJSON(`/v1/sessions/${sessionId}/message`, { text, voice_mode_enabled: voiceMode }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['session-history', variables.sessionId] })
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
    },
  })
}
