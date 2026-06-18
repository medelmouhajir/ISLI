import { useState, useRef, useEffect } from 'react'
import { cn } from '@/lib/utils'
import { Send, Clock, Terminal, Activity, ArrowRight } from 'lucide-react'
import type { Agent } from '@/types'

interface CouncilHomeViewProps {
  agents: Agent[]
  onSend: (text: string) => void | Promise<void>
  onShowHistory: () => void
  onContinueRoom?: () => void
  openRoom?: { id: string; name: string } | null
  isSending?: boolean
}

export function CouncilHomeView({
  agents,
  onSend,
  onShowHistory,
  onContinueRoom,
  openRoom,
  isSending,
}: CouncilHomeViewProps) {
  const [text, setText] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = async () => {
    if (!text.trim() || isSending) return
    const trimmed = text.trim()
    setText('')
    await onSend(trimmed)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  return (
    <div className="relative h-full w-full flex flex-col items-center justify-center bg-bg-base overflow-hidden font-mono">
      {/* Background Grids */}
      <div className="absolute inset-0 z-0 opacity-[0.03] pointer-events-none" 
           style={{ backgroundImage: 'linear-gradient(var(--border-dim) 1px, transparent 1px), linear-gradient(90deg, var(--border-dim) 1px, transparent 1px)', backgroundSize: '40px 40px' }} />
      
      {/* The Sight Line - Vertical Axis */}
      <div className="absolute left-1/2 top-0 bottom-0 w-px bg-border-dim/30 -translate-x-1/2 pointer-events-none z-0" />
      
      {/* Decorative Horizontal Axis */}
      <div className="absolute top-1/2 left-0 right-0 h-px bg-border-dim/20 -translate-y-1/2 pointer-events-none z-0" />

      <div className="relative z-10 w-full max-w-4xl px-6 flex flex-col items-center">
        {/* System Header */}
        <div className="mb-12 text-center space-y-4">
          <div className="flex flex-col items-center justify-center gap-4">
            <div className="w-16 h-16 border border-accent-cyan flex items-center justify-center bg-accent-cyan/5 text-accent-cyan shadow-glow-cyan/20">
              <Terminal className="w-8 h-8" />
            </div>
            <div className="space-y-1">
              <h1 className="text-4xl font-bold text-text-primary tracking-tighter uppercase leading-none">
                ISLI<span className="text-accent-cyan">.</span>COUNCIL
              </h1>
              <p className="text-[10px] text-accent-cyan tracking-[0.4em] uppercase font-bold">
                Unified Orchestration Command
              </p>
            </div>
          </div>
          
          <div className="flex items-center justify-center gap-6 text-[10px] uppercase tracking-widest text-text-muted font-bold">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 bg-accent-green rounded-none animate-pulse" />
              Units_Online: {agents.filter(a => a.status === 'online').length}/{agents.length}
            </div>
            <div className="w-px h-3 bg-border-dim" />
            <div className="flex items-center gap-2">
              <Activity className="w-3 h-3" />
              Primary_Node: Active
            </div>
            <div className="w-px h-3 bg-border-dim" />
            <button 
              onClick={onShowHistory}
              className="flex items-center gap-2 hover:text-accent-cyan transition-colors"
            >
              <Clock className="w-3 h-3" />
              Access_History
            </button>
          </div>
        </div>

        {/* Centered Input Container */}
        <div className="w-full relative group max-w-2xl">
          {/* Corner Ticks (Industrial Differentiator) */}
          <div className="absolute -top-3 -left-3 w-6 h-6 border-t-2 border-l-2 border-border-dim transition-colors group-focus-within:border-accent-cyan" />
          <div className="absolute -top-3 -right-3 w-6 h-6 border-t-2 border-r-2 border-border-dim transition-colors group-focus-within:border-accent-cyan" />
          <div className="absolute -bottom-3 -left-3 w-6 h-6 border-b-2 border-l-2 border-border-dim transition-colors group-focus-within:border-accent-cyan" />
          <div className="absolute -bottom-3 -right-3 w-6 h-6 border-b-2 border-r-2 border-border-dim transition-colors group-focus-within:border-accent-cyan" />

          <div className="bg-bg-surface border border-border-dim shadow-2xl p-1 transition-all group-focus-within:border-accent-cyan group-focus-within:shadow-glow-cyan/10">
            <textarea
              ref={textareaRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Enter collective command..."
              className={cn(
                "w-full bg-bg-base border-none text-xl text-text-primary placeholder:text-text-muted/20",
                "focus:ring-0 p-8 min-h-[200px] resize-none tabular-nums"
              )}
            />
            
            <div className="flex items-center justify-between p-4 bg-bg-elevated/50 border-t border-border-dim/50">
              <div className="text-[9px] text-text-muted/60 uppercase tracking-widest font-bold">
                Shift + Enter for multiline
              </div>

              <div className="flex items-center gap-3">
                {openRoom && (
                  <button
                    onClick={onContinueRoom}
                    className={cn(
                      "flex items-center gap-3 px-6 py-3 text-xs uppercase tracking-widest font-bold transition-all",
                      "border border-accent-cyan/50 text-accent-cyan hover:bg-accent-cyan/10 hover:border-accent-cyan"
                    )}
                    title={`Continue ${openRoom.name}`}
                  >
                    <ArrowRight className="w-4 h-4" />
                    Continue_Room
                  </button>
                )}

                <button
                  onClick={handleSend}
                  disabled={!text.trim() || isSending}
                  className={cn(
                    "flex items-center gap-3 px-4 md:px-8 py-3 text-xs uppercase tracking-widest font-bold transition-all",
                    text.trim() && !isSending
                      ? "bg-accent-cyan text-black hover:bg-accent-cyan/90"
                      : "bg-bg-elevated text-text-muted opacity-50 cursor-not-allowed"
                  )}
                >
                  {isSending ? (
                    <Activity className="w-4 h-4 animate-spin" />
                  ) : (
                    <Send className="w-4 h-4" />
                  )}
                  <span className="hidden md:inline">Initiate_Broadcast</span>
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Technical Footer */}
        <div className="mt-16 flex flex-col items-center gap-4">
          <div className="text-[9px] text-text-muted/30 uppercase tracking-[0.5em] font-bold">
            Terminal_Session // {new Date().toISOString().split('T')[0].replace(/-/g, '.')} // ISLI.OS v2.4.0
          </div>
          <div className="flex gap-2">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="w-1 h-1 bg-accent-cyan/20" />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

