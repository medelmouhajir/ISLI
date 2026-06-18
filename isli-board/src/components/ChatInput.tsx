import { useRef, useState, useEffect, useCallback } from 'react'
import { useVoiceRecorder } from '@/hooks/useVoiceRecorder'
import { cn } from '@/lib/utils'
import { Mic, Send, Loader2, Zap, X, Volume2, VolumeX } from 'lucide-react'

interface ChatInputProps {
  value: string
  onChange: (value: string) => void
  onSend: (text: string, voiceMode?: boolean) => void
  disabled?: boolean
  isPending?: boolean
  placeholder?: string
  voiceModeEnabled?: boolean
  onVoiceModeChange?: (enabled: boolean) => void
}

export function ChatInput({
  value,
  onChange,
  onSend,
  disabled,
  isPending,
  placeholder,
  voiceModeEnabled = false,
  onVoiceModeChange,
}: ChatInputProps) {
  const [autoSend, setAutoSend] = useState(false)
  const [recorderError, setRecorderError] = useState<string | null>(null)
  const [isFocused, setIsFocused] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const formRef = useRef<HTMLFormElement>(null)

  const {
    error: recorderErrorRaw,
    text: transcribedText,
    isRecording,
    isProcessing,
    startRecording,
    stopRecording,
    reset: resetRecorder,
  } = useVoiceRecorder()

  // When STT returns text, update the input
  useEffect(() => {
    if (transcribedText !== null) {
      if (autoSend) {
        onSend(transcribedText)
        resetRecorder()
      } else {
        onChange(transcribedText)
        textareaRef.current?.focus()
        resetRecorder()
      }
    }
  }, [transcribedText, autoSend, onChange, onSend, resetRecorder])

  // Show transient error indicator
  useEffect(() => {
    if (recorderErrorRaw) {
      setRecorderError(recorderErrorRaw)
      const t = setTimeout(() => setRecorderError(null), 4000)
      return () => clearTimeout(t)
    }
  }, [recorderErrorRaw])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!value.trim() || disabled || isPending) return
    onSend(value, voiceModeEnabled)
  }

  const handleMicClick = () => {
    if (isRecording) {
      stopRecording()
    } else {
      startRecording()
    }
  }

  const hasText = value.trim().length > 0
  const inputDisabled = disabled || isPending || isProcessing
  const isActive = isFocused || isRecording || isProcessing || hasText

  // Keyboard shortcut: Enter to send, Shift+Enter for newline
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        if (hasText && !inputDisabled) {
          onSend(value, voiceModeEnabled)
        }
      }
    },
    [hasText, inputDisabled, onSend, value, voiceModeEnabled]
  )

  return (
    <div className="relative w-full">
      {/* Error Toast */}
      <div
        className={cn(
          'absolute -top-10 left-0 right-0 flex items-center justify-center pointer-events-none transition-all duration-300',
          recorderError ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-2'
        )}
      >
        {recorderError && (
          <div className="pointer-events-auto flex items-center gap-2 px-3 py-1.5 bg-accent-red/10 border border-accent-red/30 text-accent-red text-[10px] font-mono uppercase tracking-wider shadow-lg">
            <span className="w-1.5 h-1.5 bg-accent-red animate-pulse" />
            {recorderError}
            <button
              type="button"
              onClick={() => setRecorderError(null)}
              className="ml-1 hover:text-bg-base hover:bg-accent-red transition-colors p-0.5"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        )}
      </div>

      {/* Main Command Bar */}
      <form
        ref={formRef}
        onSubmit={handleSubmit}
        className={cn(
          'relative flex items-center gap-0 transition-all duration-200',
          'bg-bg-elevated border',
          isRecording
            ? 'border-accent-red/60 shadow-[0_0_16px_rgba(255,51,102,0.15)]'
            : isProcessing
              ? 'border-accent-cyan/40'
              : isActive
                ? 'border-accent-cyan/50 shadow-[0_0_12px_rgba(0,240,255,0.08)]'
                : 'border-border-dim'
        )}
      >
        {/* Recording waveform overlay */}
        {isRecording && (
          <div className="absolute -top-px left-0 right-0 h-[2px] overflow-hidden">
            <div className="flex h-full gap-px animate-waveform">
              {Array.from({ length: 24 }).map((_, i) => (
                <span
                  key={i}
                  className="flex-1 bg-accent-red/80"
                  style={{
                    animationDelay: `${i * 40}ms`,
                  }}
                />
              ))}
            </div>
          </div>
        )}

        {/* Processing shimmer */}
        {isProcessing && (
          <div className="absolute inset-0 overflow-hidden pointer-events-none">
            <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-accent-cyan/10 to-transparent" />
          </div>
        )}

        {/* Mic Button */}
        <button
          type="button"
          onClick={handleMicClick}
          disabled={disabled || isProcessing}
          className={cn(
            'relative shrink-0 h-12 w-12 flex items-center justify-center',
            'border-r transition-all duration-200',
            isRecording
              ? 'bg-accent-red/10 border-accent-red/30 text-accent-red'
              : 'border-border-dim/50 text-text-muted hover:text-accent-cyan hover:bg-accent-cyan/5',
            (disabled || isProcessing) && 'opacity-30 cursor-not-allowed'
          )}
          title={isRecording ? 'Stop recording' : 'Voice input'}
        >
          {isProcessing ? (
            <Loader2 className="w-4 h-4 animate-spin text-accent-cyan" />
          ) : (
            <>
              <Mic className={cn('w-4 h-4 transition-transform', isRecording && 'scale-110')} />
              {isRecording && (
                <span className="absolute inset-0 border border-accent-red/40 animate-ping opacity-30" />
              )}
            </>
          )}
        </button>

        {/* Text Input */}
        <div className="flex-1 min-w-0 relative flex items-center">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder || 'ENTER COMMAND OR MESSAGE...'}
            disabled={inputDisabled}
            rows={Math.min(3, value.split('\n').length || 1)}
            className={cn(
              'w-full px-4 bg-transparent text-sm font-mono resize-none overflow-y-auto py-3.5',
              'focus:outline-none placeholder:text-text-muted/30 placeholder:font-mono placeholder:uppercase placeholder:text-[11px] placeholder:tracking-widest',
              'disabled:opacity-30 disabled:cursor-not-allowed',
              isRecording && 'text-accent-red/70'
            )}
          />

          {/* Focus tick marks — industrial aesthetic */}
          <div className="absolute top-0 left-0 w-1.5 h-1.5 border-t-2 border-l-2 border-accent-cyan opacity-0 transition-opacity duration-150 pointer-events-none"
            style={{ opacity: isFocused && !isRecording ? 1 : 0 }}
          />
          <div className="absolute bottom-0 right-0 w-1.5 h-1.5 border-b-2 border-r-2 border-accent-cyan opacity-0 transition-opacity duration-150 pointer-events-none"
            style={{ opacity: isFocused && !isRecording ? 1 : 0 }}
          />
        </div>

        {/* Right controls */}
        <div className="shrink-0 flex items-end gap-1 pr-1 pb-2 h-full">
          {/* Voice Mode toggle */}
          {onVoiceModeChange && (
            <button
              type="button"
              onClick={() => onVoiceModeChange(!voiceModeEnabled)}
              disabled={disabled || isPending}
              className={cn(
                'flex items-center gap-1.5 px-2.5 h-8 border transition-all duration-150',
                voiceModeEnabled
                  ? 'bg-accent-purple/10 border-accent-purple/40 text-accent-purple'
                  : 'bg-transparent border-border-dim/50 text-text-muted/50 hover:text-text-muted hover:border-border-dim',
                (disabled || isPending) && 'opacity-30 cursor-not-allowed'
              )}
              title={voiceModeEnabled ? 'Voice Mode ON — agent replies with audio' : 'Voice Mode OFF'}
            >
              {voiceModeEnabled ? (
                <Volume2 className="w-3 h-3" />
              ) : (
                <VolumeX className="w-3 h-3" />
              )}
              <span className="text-[9px] font-mono font-bold uppercase tracking-wider hidden sm:inline">
                {voiceModeEnabled ? 'VOICE' : 'TEXT'}
              </span>
            </button>
          )}

          {/* Auto-send toggle */}
          <button
            type="button"
            onClick={() => setAutoSend((prev) => !prev)}
            disabled={disabled || isPending}
            className={cn(
              'flex items-center gap-1.5 px-2.5 h-8 border transition-all duration-150',
              autoSend
                ? 'bg-accent-cyan/10 border-accent-cyan/40 text-accent-cyan'
                : 'bg-transparent border-border-dim/50 text-text-muted/50 hover:text-text-muted hover:border-border-dim',
              (disabled || isPending) && 'opacity-30 cursor-not-allowed'
            )}
            title={autoSend ? 'Auto-send ON — voice messages send immediately' : 'Auto-send OFF — voice messages require manual send'}
          >
            <Zap className={cn('w-3 h-3', autoSend && 'fill-accent-cyan')} />
            <span className="text-[9px] font-mono font-bold uppercase tracking-wider hidden sm:inline">
              {autoSend ? 'AUTO' : 'MANUAL'}
            </span>
          </button>

          {/* Send Button */}
          <button
            type="submit"
            disabled={!hasText || isPending || disabled}
            className={cn(
              'flex items-center justify-center h-8 border transition-all duration-200 overflow-hidden',
              hasText && !isPending && !disabled
                ? 'w-8 bg-accent-cyan border-accent-cyan text-bg-base hover:bg-accent-cyan/90 hover:shadow-[0_0_12px_rgba(0,240,255,0.25)]'
                : 'w-0 border-transparent opacity-0',
              (isPending || disabled) && 'opacity-30 cursor-not-allowed'
            )}
          >
            {isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </button>
        </div>
      </form>

      {/* Subtle hint row */}
      <div className="flex items-center justify-between mt-1.5 px-1">
        <div className="flex items-center gap-2">
          {isRecording && (
            <span className="flex items-center gap-1.5 text-[9px] font-mono text-accent-red uppercase tracking-wider animate-pulse">
              <span className="w-1.5 h-1.5 bg-accent-red rounded-full" />
              Recording...
            </span>
          )}
          {isProcessing && (
            <span className="flex items-center gap-1.5 text-[9px] font-mono text-accent-cyan uppercase tracking-wider">
              <Loader2 className="w-3 h-3 animate-spin" />
              Transcribing...
            </span>
          )}
        </div>
        <span className="text-[9px] font-mono text-text-muted/30 uppercase tracking-widest hidden sm:block">
          {navigator.platform.includes('Mac') ? '⌘' : 'Ctrl'}+Enter or Enter to send
        </span>
      </div>
    </div>
  )
}
