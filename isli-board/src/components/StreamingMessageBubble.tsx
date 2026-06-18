import { Bot } from 'lucide-react'
import { cn } from '@/lib/utils'

interface StreamingMessageBubbleProps {
  text: string
  agentPicture?: string | null
  agentName?: string
}

export function StreamingMessageBubble({ text, agentPicture, agentName }: StreamingMessageBubbleProps) {
  return (
    <div className="flex gap-3 md:gap-4 max-w-[90%] md:max-w-[80%]">
      <div
        className={cn(
          'w-8 h-8 rounded-none shrink-0 flex items-center justify-center border overflow-hidden',
          'bg-accent-cyan/5 border-accent-cyan/20 text-accent-cyan'
        )}
      >
        {agentPicture ? (
          <img
            src={`/api/v1/blobs/${agentPicture}`}
            alt={agentName || 'Agent'}
            className="w-full h-full object-cover"
          />
        ) : (
          <Bot className="w-4 h-4" />
        )}
      </div>
      <div className="bg-bg-elevated border border-border-dim p-3 md:p-4 rounded-none min-w-0 max-w-full">
        <span className="text-sm leading-relaxed font-mono whitespace-pre-wrap text-text-primary break-all">
          {text}
          <span className="inline-block w-2 h-4 bg-accent-cyan animate-pulse ml-0.5 align-middle" />
        </span>
      </div>
    </div>
  )
}
