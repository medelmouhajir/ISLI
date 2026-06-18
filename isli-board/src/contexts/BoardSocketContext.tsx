import { createContext, useContext, useMemo } from 'react'
import useWebSocket from 'react-use-websocket'
import { WS_URL } from '@/lib/constants'

export type BoardMessage =
  | { type: 'task:created'; payload: { task: Record<string, unknown> } }
  | { type: 'task:updated' | 'task:moved'; payload: { task_id: string; task: Record<string, unknown> } }
  | { type: 'agent:heartbeat' | 'agent:online'; payload: { agent_id: string } & Record<string, unknown> }
  | { type: 'session:updated' | 'session:message'; payload: { session_id: string; agent_id?: string; status?: string } }
  | { type: 'session:stream_event'; payload: { session_id: string; agent_id: string; event_type: string; data: Record<string, unknown>; timestamp: string } }
  | { type: 'keeper:inference'; payload: Record<string, unknown> }
  | { type: 'memory:journal_updated'; payload: { session_id: string; agent_id: string; old_journal: string; new_journal: string } }
  | { type: 'memory:context_injected'; payload: { session_id: string; agent_id: string; retrieved_memories: any[]; total_injected_tokens: number; threshold_used: number; fallback_triggered: boolean } }
  | { type: 'memory:context_truncated'; payload: { agent_id: string; session_id: string; warning_message: string; tokens_before: number; tokens_after: number } }
  | { type: 'notification:new'; payload: { notification_id: string; user_id: string; event_type: string; category: string; title: string; body: string | null; created_at: string | null; agent_id: string | null; task_id: string | null; session_id: string | null } }
  | { type: 'notification:read'; payload: { notification_id: string; user_id: string } }
  | { type: 'notification:read_all'; payload: { user_id: string } }
  | { type: 'room:updated'; payload: { room_id: string; status?: string | null; parent_id?: string | null } }
  | { type: 'room:agent_joined'; payload: { room_id: string; agent_id: string; agent_name?: string | null; picture?: string | null } }

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
