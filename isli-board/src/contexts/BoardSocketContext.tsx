import { createContext, useContext, useMemo } from 'react'
import useWebSocket from 'react-use-websocket'
import { WS_URL } from '@/lib/constants'

export type BoardMessage =
  | { type: 'task:created'; payload: { task: Record<string, unknown> } }
  | { type: 'task:updated' | 'task:moved'; payload: { task_id: string; task: Record<string, unknown> } }
  | { type: 'agent:heartbeat' | 'agent:online'; payload: { agent_id: string } & Record<string, unknown> }
  | { type: 'session:updated' | 'session:message'; payload: { session_id: string; agent_id?: string } }
  | { type: 'keeper:inference'; payload: Record<string, unknown> }

interface BoardSocketContextValue {
  lastMessage: BoardMessage | null
  isConnected: boolean
}

const BoardSocketContext = createContext<BoardSocketContextValue>({
  lastMessage: null,
  isConnected: false,
})

export function BoardSocketProvider({ children }: { children: React.ReactNode }) {
  const { lastJsonMessage, readyState } = useWebSocket(WS_URL, {
    shouldReconnect: () => true,
    reconnectInterval: 3000,
    reconnectAttempts: 20,
  })

  const value = useMemo<BoardSocketContextValue>(
    () => ({
      lastMessage: lastJsonMessage as BoardMessage | null,
      isConnected: readyState === WebSocket.OPEN,
    }),
    [lastJsonMessage, readyState]
  )

  return (
    <BoardSocketContext.Provider value={value}>
      {children}
    </BoardSocketContext.Provider>
  )
}

export function useBoardSocket() {
  return useContext(BoardSocketContext)
}
