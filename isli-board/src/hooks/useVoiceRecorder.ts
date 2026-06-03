import { useState, useRef, useCallback } from 'react'
import { postFormData } from '@/lib/api'

type RecordingState = 'idle' | 'recording' | 'processing' | 'error'

export function useVoiceRecorder() {
  const [state, setState] = useState<RecordingState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [text, setText] = useState<string | null>(null)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const isRecording = state === 'recording'
  const isProcessing = state === 'processing'

  const startRecording = useCallback(async () => {
    setError(null)
    setText(null)
    chunksRef.current = []

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : 'audio/mp4'

      const recorder = new MediaRecorder(stream, { mimeType })
      mediaRecorderRef.current = recorder

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data)
        }
      }

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        setState('processing')

        const blob = new Blob(chunksRef.current, { type: mimeType })
        if (blob.size === 0) {
          setError('No audio captured')
          setState('error')
          return
        }

        const formData = new FormData()
        formData.append('audio', blob, 'recording.webm')
        formData.append('language', 'auto')

        try {
          const result = await postFormData<{
            text?: string
            language?: string
            confidence?: number
            model?: string
          }>('/v1/stt/transcribe', formData)
          setText(result.text || '')
          setState('idle')
        } catch (e: unknown) {
          const msg = (e instanceof Error ? e.message : String(e)) || 'Transcription failed'
          setError(msg)
          setState('error')
        }
      }

      recorder.onerror = () => {
        stream.getTracks().forEach((t) => t.stop())
        setError('Recording error')
        setState('error')
      }

      recorder.start()
      setState('recording')
    } catch (e: unknown) {
      if ((e as Error).name === 'NotAllowedError') {
        setError('Microphone permission denied')
      } else if ((e as Error).name === 'NotFoundError') {
        setError('No microphone found')
      } else {
        setError((e as Error).message || 'Failed to start recording')
      }
      setState('error')
    }
  }, [])

  const stopRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop()
    }
  }, [])

  const reset = useCallback(() => {
    setState('idle')
    setError(null)
    setText(null)
    mediaRecorderRef.current = null
    chunksRef.current = []
  }, [])

  return {
    state,
    error,
    text,
    isRecording,
    isProcessing,
    startRecording,
    stopRecording,
    reset,
  }
}
