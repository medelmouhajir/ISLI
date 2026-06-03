import { useMemo } from 'react'
import { useBoardSocket } from '@/contexts/BoardSocketContext'

export function useSessionStream() {
  const { lastMessage } = useBoardSocket()

  return useMemo(() => {
    if (lastMessage?.type === 'session:stream_event') {
      return lastMessage.payload
    }
    return null
  }, [lastMessage])
}
