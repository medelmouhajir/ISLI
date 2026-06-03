import { useEffect, useRef, useState } from 'react'
import { useBoardSocket } from './useBoardSocket'
import { getJSON } from '@/lib/api'

export type MemoryEvent =
  | { type: 'memory:journal_updated'; payload: { session_id: string; agent_id: string; old_journal: string; new_journal: string }; timestamp: string }
  | { type: 'memory:context_injected'; payload: { session_id: string; agent_id: string; retrieved_memories: any[]; total_injected_tokens: number; threshold_used: number; fallback_triggered: boolean }; timestamp: string }
  | { type: 'memory:context_truncated'; payload: { agent_id: string; session_id: string; warning_message: string; tokens_before: number; tokens_after: number }; timestamp: string }

export function useMemoryStream(agentId?: string) {
  const { lastMessage } = useBoardSocket()
  const [events, setEvents] = useState<MemoryEvent[]>([])
  const bufferRef = useRef<MemoryEvent[]>([])

  // Fetch history on mount or when agentId changes
  useEffect(() => {
    if (!agentId) return

    const fetchHistory = async () => {
      try {
        const history = await getJSON<MemoryEvent[]>(`/v1/agents/${agentId}/memory/events`)
        bufferRef.current = history.slice(-50)
        setEvents([...bufferRef.current])
      } catch (err) {
        console.error('Failed to fetch memory history:', err)
      }
    }

    fetchHistory()
  }, [agentId])

  useEffect(() => {
    if (!lastMessage || !lastMessage.type.startsWith('memory:')) return
    
    const payload = lastMessage.payload as any
    // If agentId is provided, filter by it
    if (agentId && payload.agent_id !== agentId) return

    const event: MemoryEvent = {
      type: lastMessage.type as any,
      payload: payload,
      timestamp: (payload as any).timestamp || new Date().toISOString()
    }

    // Deduplicate: if we already have this event from history (by type and session_id or timestamp)
    // For simplicity, we'll just check if it's already in the buffer by a combination of factors
    // but in a live stream, simple push is usually okay as long as history fetch is completed.
    
    bufferRef.current = [...bufferRef.current, event].slice(-50)
    setEvents([...bufferRef.current])
  }, [lastMessage, agentId])

  return { events, setEvents }
}
