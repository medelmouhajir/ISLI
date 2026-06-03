import { Bot } from 'lucide-react'
import { cn } from '@/lib/utils'

export function StreamingMessageBubble({ text }: { text: string }) {
  return (
    <div className="flex gap-3 md:gap-4 max-w-[90%] md:max-w-[80%]">
      <div
        className={cn(
          'w-8 h-8 rounded-none shrink-0 flex items-center justify-center border',
          'bg-accent-cyan/5 border-accent-cyan/20 text-accent-cyan'
        )}
      >
        <Bot className="w-4 h-4" />
      </div>
      <div className="bg-bg-elevated border border-border-dim p-3 md:p-4 rounded-none">
        <span className="text-sm leading-relaxed font-mono whitespace-pre-wrap text-text-primary">
          {text}
          <span className="inline-block w-2 h-4 bg-accent-cyan animate-pulse ml-0.5 align-middle" />
        </span>
      </div>
    </div>
  )
}
