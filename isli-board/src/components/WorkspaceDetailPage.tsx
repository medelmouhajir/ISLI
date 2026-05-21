import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { 
  useWorkspaceFiles, 
  useReadWorkspaceFile, 
  useWriteWorkspaceFile, 
  useDeleteWorkspaceFile,
  useUploadWorkspaceFile,
  useCreateWorkspaceFolder
} from '@/hooks/useWorkspaces'
import { 
  Folder, 
  FileText, 
  ChevronRight, 
  ArrowLeft, 
  Trash2, 
  Save, 
  RefreshCw,
  HardDrive,
  FileCode,
  FileJson,
  FileTerminal,
  Upload,
  Plus,
  Download
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { Textarea } from '@/components/ui/Textarea'
import { downloadFileBlob } from '@/lib/api'
import type { WorkspaceEntry } from '@/types'

export function WorkspaceDetailPage() {
  const { id: agentId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [currentPath, setCurrentPath] = useState('')
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [editingContent, setEditingContent] = useState('')
  const [isDirty, setIsDirty] = useState(false)

  const { data, isLoading, refetch, isRefetching } = useWorkspaceFiles(agentId!, currentPath)
  const { data: fileData, isLoading: isLoadingFile } = useReadWorkspaceFile(agentId!, selectedFile ? (currentPath ? `${currentPath}/${selectedFile}` : selectedFile) : null)
  
  const writeMutation = useWriteWorkspaceFile()
  const deleteMutation = useDeleteWorkspaceFile()
  const uploadMutation = useUploadWorkspaceFile()
  const mkdirMutation = useCreateWorkspaceFolder()

  useEffect(() => {
    if (fileData?.content !== undefined) {
      setEditingContent(fileData.content)
      setIsDirty(false)
    }
  }, [fileData])

  const handleFileClick = (entry: WorkspaceEntry) => {
    if (entry.type === 'directory') {
      setCurrentPath(currentPath ? `${currentPath}/${entry.name}` : entry.name)
    } else {
      setSelectedFile(entry.name)
    }
  }

  const handleCloseEditor = () => {
    if (isDirty && !confirm('You have unsaved changes. Close anyway?')) {
      return
    }
    setSelectedFile(null)
    setEditingContent('')
    setIsDirty(false)
  }

  const handleSave = async () => {
    if (!selectedFile || !agentId) return
    const fullPath = currentPath ? `${currentPath}/${selectedFile}` : selectedFile
    try {
      await writeMutation.mutateAsync({ agentId, path: fullPath, content: editingContent })
      setIsDirty(false)
      // Success is handled by mutation's onSuccess (invalidation)
    } catch (err) {
      alert('Failed to save file: ' + (err instanceof Error ? err.message : String(err)))
    }
  }

  const handleDelete = async (e: React.MouseEvent, entry: WorkspaceEntry) => {
    e.stopPropagation()
    if (!agentId) return
    if (!confirm(`Are you sure you want to delete ${entry.name}?`)) return

    const fullPath = currentPath ? `${currentPath}/${entry.name}` : entry.name
    try {
      await deleteMutation.mutateAsync({ agentId, path: fullPath })
    } catch (err) {
      alert('Failed to delete: ' + (err instanceof Error ? err.message : String(err)))
    }
  }

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !agentId) return

    const path = currentPath ? `${currentPath}/${file.name}` : file.name
    try {
      await uploadMutation.mutateAsync({ agentId, path, file })
      if (fileInputRef.current) fileInputRef.current.value = ''
    } catch (err) {
      alert('Upload failed: ' + (err instanceof Error ? err.message : String(err)))
    }
  }

  const handleCreateFolder = async () => {
    const name = prompt('Enter folder name:')
    if (!name || !agentId) return

    const path = currentPath ? `${currentPath}/${name}` : name
    try {
      await mkdirMutation.mutateAsync({ agentId, path })
    } catch (err) {
      alert('Failed to create folder: ' + (err instanceof Error ? err.message : String(err)))
    }
  }

  const handleDownload = async (e: React.MouseEvent, entry: WorkspaceEntry) => {
    e.stopPropagation()
    if (!agentId) return

    const fullPath = currentPath ? `${currentPath}/${entry.name}` : entry.name
    try {
      await downloadFileBlob(`/v1/workspaces/${agentId}/download?path=${encodeURIComponent(fullPath)}`, entry.name)
    } catch (err) {
      alert('Download failed: ' + (err instanceof Error ? err.message : String(err)))
    }
  }

  const getFileIcon = (name: string) => {
    const ext = name.split('.').pop()?.toLowerCase()
    switch (ext) {
      case 'json': return <FileJson className="w-8 h-8 text-accent-amber" />
      case 'py':
      case 'js':
      case 'ts':
      case 'tsx': return <FileCode className="w-8 h-8 text-accent-cyan" />
      case 'sh': return <FileTerminal className="w-8 h-8 text-accent-green" />
      default: return <FileText className="w-8 h-8 text-text-muted" />
    }
  }

  const breadcrumbs = currentPath ? currentPath.split('/') : []

  return (
    <div className="flex-1 flex flex-col bg-bg-base overflow-hidden">
      {/* Toolbar */}
      <div className="border-b border-border-dim bg-bg-surface/50 p-4 md:px-8 flex items-center justify-between gap-4">
        <div className="flex items-center gap-4 overflow-hidden">
          <Button variant="ghost" size="sm" onClick={() => navigate('/workspaces')}>
            <ArrowLeft className="w-4 h-4" />
          </Button>
          
          <div className="flex items-center gap-1.5 overflow-hidden">
            <Button 
              variant="ghost" 
              size="sm" 
              className={cn("px-2 font-display font-bold", currentPath === '' ? "text-accent-cyan" : "text-text-muted")}
              onClick={() => setCurrentPath('')}
            >
              <HardDrive className="w-4 h-4 mr-2" />
              Root
            </Button>
            
            {breadcrumbs.map((part, idx) => (
              <div key={idx} className="flex items-center gap-1.5 overflow-hidden shrink-0">
                <ChevronRight className="w-3.5 h-3.5 text-text-muted/50" />
                <Button 
                  variant="ghost" 
                  size="sm" 
                  className={cn("px-2 font-display font-bold truncate max-w-[120px]", idx === breadcrumbs.length - 1 ? "text-accent-cyan" : "text-text-muted")}
                  onClick={() => setCurrentPath(breadcrumbs.slice(0, idx + 1).join('/'))}
                >
                  {part}
                </Button>
              </div>
            ))}
          </div>
        </div>

        <div className="flex items-center -space-x-px">
          <input 
            type="file" 
            ref={fileInputRef} 
            className="hidden" 
            onChange={handleUpload} 
          />
          <Button 
            variant="secondary" 
            size="sm" 
            onClick={handleCreateFolder} 
            disabled={mkdirMutation.isPending}
            className="rounded-none border-border-dim font-mono text-[10px] uppercase tracking-widest px-3"
          >
            <Plus className="w-4 h-4 sm:mr-2" />
            <span className="hidden sm:inline">New Folder</span>
          </Button>
          <Button 
            variant="secondary" 
            size="sm" 
            onClick={() => fileInputRef.current?.click()} 
            disabled={uploadMutation.isPending}
            className="rounded-none border-border-dim font-mono text-[10px] uppercase tracking-widest px-3"
          >
            <Upload className="w-4 h-4 sm:mr-2" />
            <span className="hidden sm:inline">Upload</span>
          </Button>
          <Button 
            variant="secondary" 
            size="sm" 
            onClick={() => refetch()} 
            disabled={isLoading || isRefetching}
            className="rounded-none border-border-dim font-mono text-[10px] uppercase tracking-widest px-3"
          >
            <RefreshCw className={cn("w-4 h-4 sm:mr-2", (isLoading || isRefetching) && "animate-spin")} />
            <span className="hidden sm:inline">Refresh</span>
          </Button>
        </div>
      </div>

      {/* Grid Content */}
      <div className="flex-1 overflow-y-auto p-6 md:p-8">
        {isLoading ? (
           <div className="flex flex-col items-center justify-center h-full py-20">
              <div className="w-12 h-12 border-4 border-accent-cyan/20 border-t-accent-cyan rounded-full animate-spin mb-4" />
              <span className="text-sm font-display font-medium text-text-muted animate-pulse">
                Accessing sandbox...
              </span>
           </div>
        ) : data?.entries && data.entries.length > 0 ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8 gap-4">
            {data.entries.map((entry) => (
              <div
                key={entry.name}
                onClick={() => handleFileClick(entry)}
                className={cn(
                  'group relative flex flex-col items-center p-4 rounded-xl border border-transparent transition-all cursor-pointer',
                  'hover:bg-bg-elevated hover:border-border-dim'
                )}
              >
                <div className="mb-3">
                  {entry.type === 'directory' ? (
                    <Folder className="w-10 h-10 text-accent-cyan fill-accent-cyan/10" />
                  ) : (
                    getFileIcon(entry.name)
                  )}
                </div>
                
                <span className="text-xs font-display font-medium text-text-primary text-center break-all line-clamp-2 w-full">
                  {entry.name}
                </span>

                {/* Actions overlay */}
                <div className="absolute top-2 right-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all">
                  {entry.type === 'file' && (
                    <button
                      onClick={(e) => handleDownload(e, entry)}
                      className="p-1.5 rounded-lg bg-bg-surface border border-border-dim text-accent-cyan transition-all hover:bg-accent-cyan hover:text-white"
                      title="Download"
                    >
                      <Download className="w-3.5 h-3.5" />
                    </button>
                  )}
                  <button
                    onClick={(e) => handleDelete(e, entry)}
                    className="p-1.5 rounded-lg bg-bg-surface border border-border-dim text-accent-red transition-all hover:bg-accent-red hover:text-white"
                    title="Delete"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-20 border-2 border-dashed border-border-dim rounded-3xl bg-bg-surface/30">
            <Folder className="w-16 h-16 text-text-muted mb-4 opacity-20" />
            <h3 className="text-xl font-display font-bold text-text-secondary">Workspace Empty</h3>
            <p className="text-text-muted text-center max-w-xs">
              No files or folders found in this path.
            </p>
          </div>
        )}
      </div>

      {/* File Editor Modal */}
      <Modal
        open={!!selectedFile}
        onClose={handleCloseEditor}
        title={`Editing: ${selectedFile}`}
        className="sm:max-w-4xl"
      >
        <div className="flex flex-col gap-4">
          {isLoadingFile ? (
            <div className="flex flex-col items-center justify-center py-20">
              <div className="w-8 h-8 border-4 border-accent-cyan/20 border-t-accent-cyan rounded-full animate-spin mb-2" />
              <span className="text-xs text-text-muted">Loading content...</span>
            </div>
          ) : (
            <>
              <Textarea 
                value={editingContent}
                onChange={(e) => {
                  setEditingContent(e.target.value)
                  setIsDirty(true)
                }}
                className="min-h-[400px] font-mono-data text-xs leading-relaxed"
                spellCheck={false}
              />
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs text-text-muted">
                  {isDirty && (
                    <span className="flex items-center gap-1 text-accent-amber">
                      <span className="w-1.5 h-1.5 rounded-full bg-accent-amber" />
                      Unsaved changes
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <Button variant="secondary" onClick={handleCloseEditor}>
                    Cancel
                  </Button>
                  <Button 
                    variant="primary" 
                    onClick={handleSave} 
                    disabled={!isDirty || writeMutation.isPending}
                  >
                    <Save className={cn("w-4 h-4 mr-2", writeMutation.isPending && "animate-pulse")} />
                    {writeMutation.isPending ? 'Saving...' : 'Save Changes'}
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      </Modal>
    </div>
  )
}
