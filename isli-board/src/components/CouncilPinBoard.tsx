import { useState } from 'react'
import { cn } from '@/lib/utils'
import { Pin, X, Download, FileText } from 'lucide-react'
import type { Room, RoomMessage } from '@/types'

interface CouncilPinBoardProps {
  room: Room
  onUnpin: (messageId: string) => void
  onExport: () => Promise<string>
  isExporting: boolean
}

export function CouncilPinBoard({ room, onUnpin, onExport, isExporting }: CouncilPinBoardProps) {
  const [showPreview, setShowPreview] = useState<string | null>(null)
  const msgMap = new Map<string, RoomMessage>()
  for (const m of room.messages || []) {
    msgMap.set(m.id, m)
  }

  const handleExport = async () => {
    const markdown = await onExport()
    if (!markdown) return
    const blob = new Blob([markdown], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${room.name.replace(/\s+/g, '_')}_pins.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="h-full flex flex-col bg-bg-surface/40 border-l border-border-dim">
      <div className="flex items-center justify-between px-3 py-2 border-b border-border-dim/50 bg-bg-elevated/20">
        <div className="flex items-center gap-2">
          <Pin className="w-3.5 h-3.5 text-accent-amber" />
          <span className="text-xs font-display font-bold uppercase tracking-wider text-text-primary">
            Pins
          </span>
        </div>
        {(room.pins || []).length > 0 && (
          <button
            onClick={handleExport}
            disabled={isExporting}
            className={cn(
              'flex items-center gap-1 px-2 py-1 text-[10px] font-display uppercase tracking-wider',
              'bg-bg-elevated border border-border-dim text-text-secondary',
              'hover:border-accent-cyan hover:text-accent-cyan transition-colors disabled:opacity-50'
            )}
          >
            <Download className="w-3 h-3" />
            Export
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-2">
        {(room.pins || []).length === 0 && (
          <div className="flex flex-col items-center justify-center h-32 text-text-muted">
            <FileText className="w-6 h-6 mb-2 text-text-muted/30" />
            <p className="text-[11px] text-center px-2">Pin responses to build an insight board.</p>
          </div>
        )}

        {(room.pins || []).map((pin) => {
          const msg = msgMap.get(pin.message_id)
          return (
            <div
              key={pin.message_id}
              className="group p-2 bg-bg-elevated/40 border border-border-dim hover:border-accent-amber/30 transition-colors"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 mb-1">
                    <Pin className="w-3 h-3 text-accent-amber shrink-0" />
                    <span className="text-[10px] font-display font-bold text-text-primary truncate">
                      {pin.agent_name || pin.agent_id || 'Unknown'}
                    </span>
                  </div>
                  <p
                    className="text-xs text-text-secondary line-clamp-3 cursor-pointer"
                    onClick={() => setShowPreview(showPreview === pin.message_id ? null : pin.message_id)}
                  >
                    {pin.preview || msg?.content || 'No preview'}
                  </p>
                </div>
                <button
                  onClick={() => onUnpin(pin.message_id)}
                  className="opacity-0 group-hover:opacity-100 p-1 text-text-muted hover:text-accent-red transition-opacity"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>

              {showPreview === pin.message_id && msg && (
                <div className="mt-2 p-2 bg-bg-base border border-border-dim text-xs text-text-secondary whitespace-pre-wrap max-h-48 overflow-y-auto custom-scrollbar">
                  {msg.content}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
