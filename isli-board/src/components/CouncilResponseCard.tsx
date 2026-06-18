import { useState, useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import { Pin, PinOff, Loader2, Copy, Check, Terminal, Cpu } from 'lucide-react'
import type { Agent, RoomMessage } from '@/types'
import { useBoardSocket } from '@/hooks/useBoardSocket'
import { UiComponentRenderer } from '@/components/ui/registry/UiComponentRegistry'
import { AttachmentList } from '@/components/AttachmentList'

interface CouncilResponseCardProps {
  agent: Agent
  roomId: string
  message: RoomMessage | null
  isStreaming: boolean
  isPinned: boolean
  onPin: () => void
  onUnpin: () => void
  onAction?: (actionId: string, actionType: string, payload: Record<string, unknown>) => void
}

export function CouncilResponseCard({
  agent,
  roomId,
  message,
  isStreaming,
  isPinned,
  onPin,
  onUnpin,
  onAction,
}: CouncilResponseCardProps) {
  const [streamedText, setStreamedText] = useState('')
  const [copied, setCopied] = useState(false)
  const lastSessionId = useRef<string | null>(null)
  const { lastMessage } = useBoardSocket()

  useEffect(() => {
    if (!lastMessage || lastMessage.type !== 'session:stream_event') return
    const payload = lastMessage.payload || {}
    if (payload.agent_id !== agent.id) return
    if (payload.event_type === 'token_delta' && payload.data?.delta) {
      setStreamedText((prev) => prev + payload.data.delta)
    } else if (payload.event_type === 'draft_complete') {
      setStreamedText('')
    }
  }, [lastMessage, agent.id])

  useEffect(() => {
    if (message?.id && message.id !== lastSessionId.current) {
      setStreamedText('')
      lastSessionId.current = message.id
    }
  }, [message])

  const displayText = streamedText || message?.content || ''
  const hasFinal = !!message?.content

  const handleCopy = async () => {
    if (!displayText) return
    try {
      await navigator.clipboard.writeText(displayText)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // ignore
    }
  }

  return (
    <div
      className={cn(
        'flex flex-col h-full min-h-[200px] bg-bg-surface border border-border-dim',
        'transition-all relative group/card hover:border-accent-cyan/40'
      )}
    >
      {/* Header Panel */}
      <div className="flex items-stretch justify-between h-10 border-b border-border-dim bg-bg-elevated/40">
        <div className="flex items-center min-w-0 flex-1">
          <div className="w-10 h-10 bg-bg-elevated border-r border-border-dim flex items-center justify-center shrink-0">
            {agent.picture ? (
              <img src={`/api/v1/blobs/${agent.picture}`} alt={agent.name} className="w-full h-full object-cover grayscale opacity-80 group-hover/card:grayscale-0 group-hover/card:opacity-100 transition-all" />
            ) : (
              <Cpu className="w-5 h-5 text-text-muted" />
            )}
          </div>
          <div className="px-3 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-display font-bold text-text-primary uppercase tracking-wider truncate">
                {agent.name}
              </span>
              <div className={cn(
                "w-1.5 h-1.5 shrink-0",
                agent.status === 'online' ? "bg-accent-green" : "bg-text-muted/40"
              )} />
            </div>
            <div className="text-[8px] font-display text-text-muted/40 uppercase tracking-[0.2em] truncate">
              UNIT_ID: {agent.id.split('-')[0]}
            </div>
          </div>
        </div>

        <div className="flex items-center bg-bg-elevated/20">
          {isStreaming && (
            <div className="px-3 flex items-center gap-2 border-l border-border-dim text-[9px] font-display text-accent-cyan animate-pulse whitespace-nowrap">
              <Terminal className="w-3 h-3" />
              [LIVE_FEED]
            </div>
          )}
          <div className="flex items-center h-full border-l border-border-dim">
            <button
              onClick={handleCopy}
              disabled={!displayText}
              className="w-10 h-10 flex items-center justify-center text-text-muted hover:text-accent-cyan hover:bg-accent-cyan/5 disabled:opacity-20 transition-colors"
              title="COPY_BUFFER"
            >
              {copied ? <Check className="w-4 h-4 text-accent-green" /> : <Copy className="w-4 h-4" />}
            </button>
            <button
              onClick={isPinned ? onUnpin : onPin}
              disabled={!hasFinal}
              className={cn(
                'w-10 h-10 flex items-center justify-center border-l border-border-dim transition-colors',
                isPinned 
                  ? 'bg-accent-amber/10 text-accent-amber' 
                  : 'text-text-muted hover:text-accent-amber hover:bg-accent-amber/5'
              )}
              title={isPinned ? 'RELEASE_PIN' : 'SECURE_PIN'}
            >
              {isPinned ? <PinOff className="w-4 h-4" /> : <Pin className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </div>

      {/* Output Buffer */}
      <div className="flex-1 p-4 overflow-y-auto custom-scrollbar bg-bg-base/30">
        {displayText ? (
          <div className="text-sm text-text-secondary whitespace-pre-wrap leading-relaxed font-mono selection:bg-accent-cyan/30">
            {displayText}
            {isStreaming && (
              <span className="inline-block w-2 h-4 ml-1 bg-accent-cyan animate-pulse align-middle" />
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-8 gap-3 opacity-20">
            <Loader2 className="w-6 h-6 animate-spin text-accent-cyan" />
            <span className="text-[9px] font-display uppercase tracking-[0.3em]">Awaiting_Signal...</span>
          </div>
        )}

        {message?.components && message.components.length > 0 && (
          <div className="mt-6 pt-6 border-t border-border-dim/30 space-y-4">
             <div className="text-[8px] font-display text-text-muted/40 uppercase tracking-[0.2em] mb-2">
              ACTIVE_MODULES
            </div>
            {message.components.map((component, idx) => (
              <UiComponentRenderer
                key={idx}
                payload={component}
                sessionId={`room:${roomId}:${agent.id}`}
                onAction={onAction || (() => {})}
              />
            ))}
          </div>
        )}

        {message?.attachments && message.attachments.length > 0 && (
          <div className="mt-6 pt-6 border-t border-border-dim/30">
            <div className="text-[8px] font-display text-text-muted/40 uppercase tracking-[0.2em] mb-2">
              DATA_ATTACHMENTS
            </div>
            <AttachmentList attachments={message.attachments} />
          </div>
        )}

        {message?.audio_url && (
          <div className="mt-6 pt-6 border-t border-border-dim/30">
            <div className="text-[8px] font-display text-text-muted/40 uppercase tracking-[0.2em] mb-2">
              AUDIO_RECORD
            </div>
            <audio controls src={message.audio_url} className="w-full h-8 grayscale opacity-60 hover:opacity-100 transition-opacity" />
          </div>
        )}
      </div>

      {/* Decorative footer line */}
      <div className="h-0.5 w-full bg-border-dim/10" />
    </div>
  )
}
