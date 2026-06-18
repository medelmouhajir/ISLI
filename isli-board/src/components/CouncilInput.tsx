import { useState, useRef, useEffect, useMemo, KeyboardEvent } from 'react'
import { cn } from '@/lib/utils'
import { Send, X, ChevronDown, Target, Zap } from 'lucide-react'
import type { Agent } from '@/types'

interface CouncilInputProps {
  agents: Agent[]
  addressedAgentIds: string[]
  onAddressedChange: (ids: string[]) => void
  onSend: (text: string) => void | Promise<void>
  disabled?: boolean
  placeholder?: string
  isHero?: boolean
}

export function CouncilInput({
  agents,
  addressedAgentIds,
  onAddressedChange,
  onSend,
  disabled,
  placeholder = 'COMMAND://',
  isHero,
}: CouncilInputProps) {
  const [text, setText] = useState('')
  const [pickerOpen, setPickerOpen] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const mentionIds = useMemo(() => {
    const tokens = [...(text || '').matchAll(/@([a-zA-Z0-9_\-]+)/g)].map((m) => m[1].toLowerCase())
    const hasAll = tokens.includes('all') || tokens.includes('everyone')
    if (hasAll) return agents.map((a) => a.id)
    return agents
      .filter((a) => {
        const nameToken = a.name?.toLowerCase().split(' ')[0]
        const idToken = a.id.toLowerCase()
        return tokens.includes(nameToken) || tokens.includes(idToken)
      })
      .map((a) => a.id)
  }, [text, agents])

  useEffect(() => {
    const missing = mentionIds.filter((id) => !addressedAgentIds.includes(id))
    if (missing.length > 0) {
      onAddressedChange([...addressedAgentIds, ...missing])
    }
  }, [mentionIds, addressedAgentIds, onAddressedChange])

  const addressedAgents = agents.filter((a) => addressedAgentIds.includes(a.id))
  const availableAgents = agents.filter((a) => !addressedAgentIds.includes(a.id))

  const handleSend = async () => {
    if (!text.trim() || disabled) return
    const trimmed = text.trim()
    setText('')
    onAddressedChange([])
    await onSend(trimmed)
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const toggleAgent = (agentId: string) => {
    if (addressedAgentIds.includes(agentId)) {
      onAddressedChange(addressedAgentIds.filter((id) => id !== agentId))
    } else {
      onAddressedChange([...addressedAgentIds, agentId])
    }
  }

  return (
    <div className={cn(
      "bg-bg-surface border border-border-dim transition-colors group",
      isHero ? "p-0" : "m-3 md:m-4"
    )}>
      {/* Target Header */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border-dim bg-bg-elevated/40">
        <div className="flex items-center gap-2 overflow-hidden">
          <div className="flex items-center gap-1.5 text-[10px] font-display uppercase tracking-widest text-text-muted shrink-0">
            <Target className="w-3 h-3 text-accent-cyan" />
            Targets // {addressedAgents.length}
          </div>
          <div className="flex items-center gap-1 overflow-x-auto no-scrollbar py-0.5">
            {addressedAgents.length > 0 ? (
              addressedAgents.map((agent) => (
                <button
                  key={agent.id}
                  onClick={() => toggleAgent(agent.id)}
                  disabled={disabled}
                  className="flex items-center gap-1 px-1.5 py-0.5 bg-accent-cyan/10 border border-accent-cyan/20 text-[10px] font-display text-accent-cyan hover:bg-accent-cyan/20 transition-colors whitespace-nowrap"
                >
                  {agent.name.toUpperCase()}
                  <X className="w-2.5 h-2.5" />
                </button>
              ))
            ) : (
              <span className="text-[10px] font-display text-text-muted/40 italic">
                NO_UNITS_ADDRESSED
              </span>
            )}
          </div>
        </div>

        {!isHero && (
          <div className="relative shrink-0 ml-4">
            <button
              onClick={() => setPickerOpen((v) => !v)}
              disabled={disabled || availableAgents.length === 0}
              className="flex items-center gap-1 text-[10px] font-display uppercase tracking-tighter text-text-muted hover:text-text-primary transition-colors disabled:opacity-30"
            >
              [+]_TARGET
              <ChevronDown className={cn("w-3 h-3 transition-transform", pickerOpen && "rotate-180")} />
            </button>
            {pickerOpen && availableAgents.length > 0 && (
              <div className="absolute bottom-full right-0 mb-2 w-48 bg-bg-surface border border-border-dim shadow-2xl z-50 overflow-hidden">
                <div className="px-3 py-1 bg-bg-elevated border-b border-border-dim text-[9px] font-display text-text-muted uppercase tracking-widest">
                  Available Units
                </div>
                {availableAgents.map((agent) => (
                  <button
                    key={agent.id}
                    onClick={() => {
                      toggleAgent(agent.id)
                      setPickerOpen(false)
                      textareaRef.current?.focus()
                    }}
                    className="w-full text-left px-3 py-2 text-xs font-display text-text-secondary hover:bg-accent-cyan/10 hover:text-accent-cyan transition-colors"
                  >
                    {agent.name.toUpperCase()}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Input Area */}
      <div className="relative bg-bg-base flex">
        <div className="w-1 bg-transparent group-focus-within:bg-accent-cyan transition-colors shrink-0" />
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={placeholder}
          rows={1}
          className={cn(
            'w-full resize-none rounded-none bg-transparent border-none',
            'text-text-primary placeholder:text-text-muted/20 transition-all font-mono',
            'focus:outline-none focus:ring-0',
            isHero ? 'text-lg p-8 min-h-[160px]' : 'text-sm p-4 min-h-[56px]',
            'disabled:opacity-50'
          )}
          style={{ maxHeight: 240 }}
          onInput={(e) => {
            if (isHero) return
            const target = e.target as HTMLTextAreaElement
            target.style.height = 'auto'
            target.style.height = `${Math.min(target.scrollHeight, 240)}px`
          }}
        />
      </div>

      {/* Action Strip */}
      <div className="flex items-stretch border-t border-border-dim bg-bg-elevated/20">
        <div className="flex-1 flex items-center px-4 gap-4 overflow-hidden">
          <div className="flex items-center gap-1.5 text-[9px] font-display text-text-muted/60 uppercase tracking-widest whitespace-nowrap">
            <Zap className="w-2.5 h-2.5" />
            Protocol: Mention_Capture
          </div>
          <div className="hidden sm:block h-3 w-px bg-border-dim/30 shrink-0" />
          <div className="hidden sm:flex items-center gap-1 text-[9px] font-display text-text-muted/40 uppercase tracking-widest truncate">
            Shift+Enter for newline
          </div>
        </div>

        <button
          onClick={handleSend}
          disabled={disabled || !text.trim()}
          className={cn(
            'px-6 flex items-center justify-center gap-2 text-xs font-display uppercase tracking-widest transition-all',
            'border-l border-border-dim',
            text.trim() && !disabled 
              ? 'bg-accent-cyan text-black hover:bg-white' 
              : 'bg-bg-elevated text-text-muted/40',
            isHero ? 'h-14 min-w-[160px]' : 'h-11 min-w-[120px]'
          )}
        >
          EXECUTE
          <Send className={cn("w-3.5 h-3.5", text.trim() && !disabled && "animate-pulse")} />
        </button>
      </div>

      {/* Overlay for picker */}
      {pickerOpen && (
        <div className="fixed inset-0 z-40" onClick={() => setPickerOpen(false)} />
      )}
    </div>
  )
}

