import { useState } from 'react'
import { Download, Eye, FileText, FileImage, FileAudio, FileVideo, File } from 'lucide-react'
import { Modal } from '@/components/ui/Modal'
import { cn, formatBytes, resolveApiUrl } from '@/lib/utils'
import type { ComponentPayload } from '@/types'

interface FileCardProps {
  payload: ComponentPayload
}

export function FileCard({ payload }: FileCardProps) {
  const props = payload.props as Record<string, unknown>
  const filename = String(props.filename || props.title || 'File')
  const mimeType = String(props.mime_type || 'application/octet-stream')
  const downloadUrl = resolveApiUrl(String(props.download_url || props.url || ''))
  const sizeBytes = typeof props.size_bytes === 'number' ? props.size_bytes : null
  const caption = props.caption ? String(props.caption) : null
  const [previewOpen, setPreviewOpen] = useState(false)

  const category = mimeType.split('/')[0]
  const Icon =
    category === 'image'
      ? FileImage
      : category === 'audio'
        ? FileAudio
        : category === 'video'
          ? FileVideo
          : category === 'text'
            ? FileText
            : File

  const isImage = category === 'image'
  const isPdf = mimeType === 'application/pdf'
  const canPreview = isImage || isPdf || category === 'video' || category === 'audio' || category === 'text'

  return (
    <>
      <div
        className={cn(
          'flex items-center gap-3 p-3 border bg-bg-elevated/50 hover:bg-bg-elevated',
          'border-border-dim text-text-primary transition-colors'
        )}
      >
        <div className="shrink-0">
          <Icon className="w-8 h-8 text-accent-cyan" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium truncate">{filename}</div>
          {sizeBytes !== null && (
            <div className="text-[10px] font-mono text-text-muted uppercase">
              {formatBytes(sizeBytes)} · {mimeType}
            </div>
          )}
          {caption && (
            <div className="text-xs text-text-muted mt-1 truncate">{caption}</div>
          )}
        </div>
        <div className="shrink-0 flex items-center gap-1">
          {canPreview && (
            <button
              onClick={() => setPreviewOpen(true)}
              className="p-2 hover:bg-accent-cyan/10 text-text-muted hover:text-accent-cyan transition-colors"
              title="Preview"
            >
              <Eye className="w-4 h-4" />
            </button>
          )}
          <a
            href={downloadUrl}
            download={filename}
            className="p-2 hover:bg-accent-cyan/10 text-text-muted hover:text-accent-cyan transition-colors"
            title="Download"
          >
            <Download className="w-4 h-4" />
          </a>
        </div>
      </div>

      {previewOpen && (
        <Modal
          open={previewOpen}
          onClose={() => setPreviewOpen(false)}
          title={filename}
          className="sm:max-w-4xl"
        >
          <div className="w-full min-h-[200px] max-h-[70vh] flex items-center justify-center bg-bg-base overflow-auto">
            {isImage ? (
              <img
                src={downloadUrl}
                alt={filename}
                className="max-w-full max-h-[70vh] object-contain"
              />
            ) : category === 'video' ? (
              <video controls className="max-w-full max-h-[70vh]">
                <source src={downloadUrl} type={mimeType} />
              </video>
            ) : category === 'audio' ? (
              <audio controls className="w-full">
                <source src={downloadUrl} type={mimeType} />
              </audio>
            ) : (
              <iframe
                src={downloadUrl}
                title={filename}
                className="w-full h-[70vh] border-0"
              />
            )}
          </div>
        </Modal>
      )}
    </>
  )
}
