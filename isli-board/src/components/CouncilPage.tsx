import { useState, useEffect, useCallback, useMemo } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Modal } from './ui/Modal'
import { CouncilRoomList } from './CouncilRoomList'
import { CouncilRoom } from './CouncilRoom'
import { CouncilHomeView } from './CouncilHomeView'
import { useAgents } from '@/hooks/useAgents'
import {
  useRooms,
  useRoom,
  useCreateRoom,
  useSendRoomMessage,
  useAddRoomAgent,
  useCloseRoom,
  usePinMessage,
  useUnpinMessage,
} from '@/hooks/useRooms'
import { useSessionAction } from '@/hooks/useSessionAction'
import { useBoardSocket } from '@/hooks/useBoardSocket'

export function CouncilPage() {
  const queryClient = useQueryClient()
  const { data: rooms = [] } = useRooms()
  const { data: agents = [] } = useAgents()
  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const { data: selectedRoom } = useRoom(selectedRoomId)
  const { lastMessage } = useBoardSocket()

  const createRoom = useCreateRoom()
  const sendMessage = useSendRoomMessage()
  const addAgent = useAddRoomAgent()
  const closeRoom = useCloseRoom()
  const pinMessage = usePinMessage()
  const unpinMessage = useUnpinMessage()
  const sessionAction = useSessionAction()

  // WebSocket real-time updates for rooms
  useEffect(() => {
    if (!lastMessage) return
    if (lastMessage.type === 'room:updated' || lastMessage.type === 'room:agent_joined') {
      const roomId = lastMessage.payload?.room_id
      if (roomId) {
        // Invalidate specific room details
        queryClient.invalidateQueries({ queryKey: ['rooms', roomId] })
        queryClient.invalidateQueries({ queryKey: ['room-history', roomId] })
      }
      // Always invalidate the rooms list to catch status/timestamp updates
      queryClient.invalidateQueries({ queryKey: ['rooms'] })
    }
  }, [lastMessage, queryClient])

  const activeRoom = selectedRoom || rooms.find((r) => r.id === selectedRoomId)

  const newestActiveRoom = useMemo(() => {
    const active = rooms.filter((r) => r.status === 'active')
    if (active.length === 0) return null
    return active.sort(
      (a, b) =>
        new Date(b.last_activity_at || b.created_at).getTime() -
        new Date(a.last_activity_at || a.created_at).getTime()
    )[0]
  }, [rooms])

  const handleContinueRoom = () => {
    if (!newestActiveRoom) return
    setSelectedRoomId(newestActiveRoom.id)
  }

  const handleCreate = async (name: string, agentIds: string[]) => {
    try {
      const room = await createRoom.mutateAsync({ name, agent_ids: agentIds })
      setSelectedRoomId(room.id)
      setShowHistory(false)
    } catch (err) {
      console.error('Failed to create room:', err)
    }
  }

  const handleSend = async (text: string, addressedAgentIds?: string[]) => {
    if (!activeRoom) {
      // Logic for CouncilHomeView "Broadcast"
      
      // Parse mentions from the text manually for initial room creation
      const mentionRegex = /@([a-zA-Z0-9_\-]+)/g
      const mentionedTokens = [...text.matchAll(mentionRegex)].map(m => m[1].toLowerCase())
      
      let targetAgentIds: string[] = []
      
      if (mentionedTokens.length > 0) {
        // Find agents matching mentioned tokens (by name or ID)
        targetAgentIds = agents
          .filter(a => {
            const nameToken = a.name?.toLowerCase().split(' ')[0]
            const idToken = a.id.toLowerCase()
            return mentionedTokens.includes(nameToken) || mentionedTokens.includes(idToken)
          })
          .map(a => a.id)
      }

      // Fallback: use all online agents if no specific mentions
      if (targetAgentIds.length === 0) {
        targetAgentIds = agents
          .filter((a) => a.status === 'online')
          .map((a) => a.id)
      }
      
      const roomName = text.length > 20 ? text.substring(0, 17) + '...' : text
      
      try {
        const room = await createRoom.mutateAsync({ 
          name: roomName, 
          agent_ids: targetAgentIds 
        })
        setSelectedRoomId(room.id)
        await sendMessage.mutateAsync({
          roomId: room.id,
          text,
          addressedAgentIds: targetAgentIds,
        })
      } catch (err) {
        console.error('Failed to broadcast message:', err)
      }
      return
    }

    await sendMessage.mutateAsync({
      roomId: activeRoom.id,
      text,
      addressedAgentIds,
    })
  }

  const handleAddAgent = async (agentId: string) => {
    if (!activeRoom) return
    await addAgent.mutateAsync({ roomId: activeRoom.id, agentId })
  }

  const handleClose = async () => {
    if (!activeRoom) return
    const roomId = activeRoom.id
    setSelectedRoomId(null)
    try {
      await closeRoom.mutateAsync(roomId)
    } catch (err) {
      console.error('Failed to close room:', err)
    }
  }

  const handlePin = async (messageId: string) => {
    if (!activeRoom) return
    await pinMessage.mutateAsync({ roomId: activeRoom.id, messageId })
  }

  const handleUnpin = async (messageId: string) => {
    if (!activeRoom) return
    await unpinMessage.mutateAsync({ roomId: activeRoom.id, messageId })
  }

  const handleComponentAction = useCallback(
    (
      sessionId: string,
      actionId: string,
      actionType: string,
      payload: Record<string, unknown>
    ) => {
      sessionAction.mutate({
        sessionId,
        action: { action_id: actionId, action_type: actionType, payload },
      })
    },
    [sessionAction]
  )

  return (
    <div className="h-full flex-1 flex relative overflow-hidden bg-bg-base">
      <Modal
        open={showHistory}
        onClose={() => setShowHistory(false)}
        title="Council History"
        className="sm:max-w-lg"
        noPadding
      >
        <div className="h-[60vh]">
          <CouncilRoomList
            rooms={rooms}
            agents={agents}
            selectedRoomId={selectedRoomId}
            onSelect={(id) => {
              setSelectedRoomId(id)
              setShowHistory(false)
            }}
            onCreate={handleCreate}
            onClose={handleClose}
            isCreating={createRoom.isPending}
          />
        </div>
      </Modal>

      {/* Main Content - Full Width */}
      <div className="flex-1 min-w-0 relative h-full">
        {activeRoom ? (
          <CouncilRoom
            room={activeRoom}
            agents={agents}
            onBack={() => setSelectedRoomId(null)}
            onAddAgent={handleAddAgent}
            onSendMessage={handleSend}
            onClose={handleClose}
            onPin={handlePin}
            onUnpin={handleUnpin}
            onShowHistory={() => setShowHistory(true)}
            onComponentAction={handleComponentAction}
            isSending={sendMessage.isPending}
            isAddingAgent={addAgent.isPending}
            isClosing={closeRoom.isPending}
          />
        ) : (
          <CouncilHomeView
            agents={agents}
            onSend={handleSend}
            onShowHistory={() => setShowHistory(true)}
            onContinueRoom={handleContinueRoom}
            openRoom={newestActiveRoom}
            isSending={sendMessage.isPending || createRoom.isPending}
          />
        )}
      </div>
    </div>
  )
}

