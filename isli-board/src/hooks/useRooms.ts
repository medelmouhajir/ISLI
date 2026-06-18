import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getJSON, postJSON, deleteJSON } from '@/lib/api'
import type { Room, RoomHistory } from '@/types'

const BOARD_USER_ID = 'isli-board-user'

function getUserId(): string {
  try {
    return localStorage.getItem('isli-user-id') || BOARD_USER_ID
  } catch {
    return BOARD_USER_ID
  }
}

export function useRooms() {
  const userId = getUserId()
  return useQuery<Room[]>({
    queryKey: ['rooms', userId],
    queryFn: () => getJSON(`/v1/rooms?user_id=${encodeURIComponent(userId)}`),
    staleTime: 30000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
}

export function useRoom(roomId: string | null) {
  const userId = getUserId()
  return useQuery<Room>({
    queryKey: ['rooms', roomId],
    queryFn: () => {
      if (!roomId) throw new Error('No room ID')
      return getJSON(`/v1/rooms/${roomId}?user_id=${encodeURIComponent(userId)}`)
    },
    enabled: !!roomId,
    staleTime: 30000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
}

export function useRoomHistory(roomId: string | null) {
  const userId = getUserId()
  return useQuery<RoomHistory>({
    queryKey: ['room-history', roomId],
    queryFn: () => {
      if (!roomId) throw new Error('No room ID')
      return getJSON(`/v1/rooms/${roomId}/history?user_id=${encodeURIComponent(userId)}`)
    },
    enabled: !!roomId,
    staleTime: 30000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
}

export function useCreateRoom() {
  const queryClient = useQueryClient()
  const userId = getUserId()
  return useMutation({
    mutationFn: (payload: { name: string; agent_ids: string[]; metadata?: Record<string, unknown> }): Promise<Room> =>
      postJSON('/v1/rooms', { ...payload, user_id: userId, channel: 'web' }),
    onSuccess: (newRoom) => {
      queryClient.setQueryData(['rooms', userId], (old: Room[] | undefined) => {
        if (!old) return [newRoom]
        return [newRoom, ...old]
      })
      queryClient.invalidateQueries({ queryKey: ['rooms'] })
    },
  })
}

export function useSendRoomMessage() {
  const queryClient = useQueryClient()
  const userId = getUserId()
  return useMutation({
    mutationFn: ({
      roomId,
      text,
      addressedAgentIds,
      metadata,
    }: {
      roomId: string
      text: string
      addressedAgentIds?: string[]
      metadata?: Record<string, unknown>
    }) =>
      postJSON(`/v1/rooms/${roomId}/message`, {
        text,
        user_id: userId,
        addressed_agent_ids: addressedAgentIds,
        metadata,
      }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['rooms', variables.roomId] })
      queryClient.invalidateQueries({ queryKey: ['room-history', variables.roomId] })
    },
  })
}

export function useAddRoomAgent() {
  const queryClient = useQueryClient()
  const userId = getUserId()
  return useMutation({
    mutationFn: ({ roomId, agentId }: { roomId: string; agentId: string }) =>
      postJSON(`/v1/rooms/${roomId}/agents`, { agent_id: agentId, user_id: userId }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['rooms', variables.roomId] })
      queryClient.invalidateQueries({ queryKey: ['room-history', variables.roomId] })
    },
  })
}

export function useCloseRoom() {
  const queryClient = useQueryClient()
  const userId = getUserId()
  return useMutation({
    mutationFn: (roomId: string) =>
      postJSON(`/v1/rooms/${roomId}/close?user_id=${encodeURIComponent(userId)}`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rooms'] })
    },
  })
}

export function usePinMessage() {
  const queryClient = useQueryClient()
  const userId = getUserId()
  return useMutation({
    mutationFn: ({ roomId, messageId }: { roomId: string; messageId: string }) =>
      postJSON(`/v1/rooms/${roomId}/pin`, { message_id: messageId, user_id: userId }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['rooms', variables.roomId] })
      queryClient.invalidateQueries({ queryKey: ['room-history', variables.roomId] })
    },
  })
}

export function useUnpinMessage() {
  const queryClient = useQueryClient()
  const userId = getUserId()
  return useMutation({
    mutationFn: ({ roomId, messageId }: { roomId: string; messageId: string }) =>
      deleteJSON(`/v1/rooms/${roomId}/pin/${messageId}?user_id=${encodeURIComponent(userId)}`),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['rooms', variables.roomId] })
      queryClient.invalidateQueries({ queryKey: ['room-history', variables.roomId] })
    },
  })
}

export function useExportPins() {
  const userId = getUserId()
  return useMutation({
    mutationFn: async (roomId: string): Promise<string> => {
      const res = await postJSON<{ markdown: string }>(
        `/v1/rooms/${roomId}/export-pins`,
        { user_id: userId }
      )
      return res.markdown
    },
  })
}
