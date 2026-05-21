import { useEffect, useRef, useState } from 'react'
import { useBoardSocket } from './useBoardSocket'
import type { KeeperInference } from '@/types'

export function useKeeperStream() {
  const { lastMessage } = useBoardSocket()
  const [entries, setEntries] = useState<KeeperInference[]>([])
  const bufferRef = useRef<KeeperInference[]>([])

  useEffect(() => {
    if (!lastMessage || lastMessage.type !== 'keeper:inference') return
    const payload = lastMessage.payload as unknown as KeeperInference
    bufferRef.current = [...bufferRef.current, payload].slice(-50)
    setEntries([...bufferRef.current])
  }, [lastMessage])

  return { entries }
}
