import { useState } from 'react'
import { useSharedWorkspaces, useCreateSharedWorkspace, useDeleteSharedWorkspace } from '@/hooks/useSharedWorkspaces'
import { useAgents } from '@/hooks/useAgents'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { ConfirmationModal } from '@/components/ui/ConfirmationModal'
import { cn } from '@/lib/utils'
import { Link } from 'react-router-dom'
import {
  Users,
  HardDrive,
  ArrowRight,
  Plus,
  Trash2,
  FolderHeart,
  Bot,
  Loader2,
} from 'lucide-react'

export function SharedWorkspacesPage() {
  const { data: workspaces = [], isLoading } = useSharedWorkspaces()
  const { data: agents = [] } = useAgents()
  const createMutation = useCreateSharedWorkspace()
  const deleteMutation = useDeleteSharedWorkspace()

  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [ownerId, setOwnerId] = useState('')
  const [confirmModal, setConfirmModal] = useState<{
    open: boolean;
    title: string;
    description: string;
    onConfirm: () => void | Promise<void>;
  }>({
    open: false,
    title: '',
    description: '',
    onConfirm: () => {},
  })

  const handleCreate = async () => {
    if (!name.trim() || !ownerId) return
    try {
      await createMutation.mutateAsync({
        name: name.trim(),
        description: description.trim() || undefined,
        owner_id: ownerId,
      })
      setShowCreate(false)
      setName('')
      setDescription('')
      setOwnerId('')
    } catch (err) {
      alert('Failed to create workspace: ' + (err instanceof Error ? err.message : String(err)))
    }
  }

  const handleDelete = async (id: string, wsName: string) => {
    setConfirmModal({
      open: true,
      title: 'Delete Shared Workspace',
      description: `Are you sure you want to delete shared workspace "${wsName}"? This action cannot be undone and will permanently remove all files and member associations.`,
      onConfirm: async () => {
        try {
          await deleteMutation.mutateAsync(id)
        } catch (err) {
          alert('Failed to delete workspace: ' + (err instanceof Error ? err.message : String(err)))
        }
      },
    })
  }

  return (
    <div className="flex-1 overflow-y-auto bg-bg-base p-6 md:p-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-display font-bold text-text-primary flex items-center gap-3">
            <Users className="w-8 h-8 text-accent-cyan" />
            Shared Workspaces
          </h1>
          <p className="text-text-secondary mt-1 max-w-xl">
            Collaborative file spaces shared across agents. Promote task outputs here for cross-agent access.
          </p>
        </div>
        <Button variant="primary" size="sm" onClick={() => setShowCreate(true)}>
          <Plus className="w-4 h-4 mr-2" />
          New Workspace
        </Button>
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20">
          <div className="w-12 h-12 border-4 border-accent-cyan/20 border-t-accent-cyan rounded-full animate-spin mb-4" />
          <span className="text-sm font-display font-medium text-text-muted animate-pulse">
            Loading workspaces...
          </span>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {workspaces.map((ws) => (
            <div
              key={ws.id}
              className={cn(
                'group flex flex-col p-5 rounded-2xl bg-bg-surface border border-border-dim',
                'hover:border-accent-cyan hover:shadow-card-hover hover:-translate-y-1',
                'transition-all duration-300 relative overflow-hidden'
              )}
            >
              <div className="absolute top-0 right-0 p-8 -mr-8 -mt-8 opacity-[0.03] group-hover:opacity-[0.07] transition-opacity">
                <HardDrive className="w-32 h-32" />
              </div>

              <div className="flex items-start justify-between mb-4 relative z-10">
                <div className="w-12 h-12 rounded-xl bg-bg-elevated border border-border-dim flex items-center justify-center text-accent-cyan group-hover:border-accent-cyan/50 transition-colors">
                  <FolderHeart className="w-6 h-6" />
                </div>
                <button
                  onClick={() => handleDelete(ws.id, ws.name)}
                  className="p-2 rounded-lg bg-bg-elevated border border-border-dim text-accent-red transition-all hover:bg-accent-red hover:text-white"
                  title="Delete workspace"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>

              <div className="mb-4 relative z-10">
                <Link to={`/shared-workspaces/${ws.id}`}>
                  <h3 className="text-lg font-display font-bold text-text-primary group-hover:text-accent-cyan transition-colors truncate">
                    {ws.name}
                  </h3>
                </Link>
                {ws.description && (
                  <p className="text-xs text-text-muted mt-1 line-clamp-2">{ws.description}</p>
                )}
                <p className="text-xs font-mono-data text-text-muted mt-1 uppercase tracking-tighter">
                  {ws.id}
                </p>
              </div>

              <div className="mt-auto relative z-10 pt-4 border-t border-border-dim space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-text-secondary">Owner</span>
                  <span className="font-mono-data text-text-primary">
                    {agents.find((a) => a.id === ws.owner_id)?.name || ws.owner_id}
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-text-secondary">Members</span>
                  <span className="font-mono-data text-text-primary">{ws.members.length}</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-text-secondary">Quota</span>
                  <span className="font-mono-data text-text-primary">{(ws.quota_bytes / 1024 / 1024).toFixed(0)} MB</span>
                </div>
                <Link
                  to={`/shared-workspaces/${ws.id}`}
                  className="flex items-center justify-between pt-2 mt-2 border-t border-border-dim/50"
                >
                  <span className="text-xs text-text-secondary">Manage</span>
                  <div className="text-accent-cyan opacity-0 group-hover:opacity-100 transform translate-x-2 group-hover:translate-x-0 transition-all">
                    <ArrowRight className="w-5 h-5" />
                  </div>
                </Link>
              </div>
            </div>
          ))}

          {workspaces.length === 0 && (
            <div className="col-span-full flex flex-col items-center justify-center py-20 border-2 border-dashed border-border-dim rounded-3xl bg-bg-surface/30">
              <Bot className="w-16 h-16 text-text-muted mb-4 opacity-20" />
              <h3 className="text-xl font-display font-bold text-text-secondary">No Shared Workspaces</h3>
              <p className="text-text-muted text-center max-w-xs">
                Create a shared workspace to collaborate across agents.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Create Modal */}
      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Create Shared Workspace">
        <div className="space-y-4 w-[400px]">
          <div>
            <label className="text-xs font-display uppercase tracking-wider text-text-secondary block mb-1.5">
              Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-bg-elevated border border-border-dim rounded-lg px-3 py-2 text-sm text-text-primary focus:border-accent-cyan focus:outline-none"
              placeholder="e.g. Project Alpha"
            />
          </div>
          <div>
            <label className="text-xs font-display uppercase tracking-wider text-text-secondary block mb-1.5">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full bg-bg-elevated border border-border-dim rounded-lg px-3 py-2 text-sm text-text-primary focus:border-accent-cyan focus:outline-none min-h-[80px]"
              placeholder="Optional description"
            />
          </div>
          <div>
            <label className="text-xs font-display uppercase tracking-wider text-text-secondary block mb-1.5">
              Owner Agent
            </label>
            <select
              value={ownerId}
              onChange={(e) => setOwnerId(e.target.value)}
              className="w-full bg-bg-elevated border border-border-dim rounded-lg px-3 py-2 text-sm text-text-primary focus:border-accent-cyan focus:outline-none"
            >
              <option value="">Select an agent</option>
              {agents.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <Button variant="secondary" size="sm" onClick={() => setShowCreate(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleCreate}
              disabled={!name.trim() || !ownerId || createMutation.isPending}
            >
              {createMutation.isPending ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Plus className="w-4 h-4 mr-2" />
              )}
              Create
            </Button>
          </div>
        </div>
      </Modal>
      <ConfirmationModal
        open={confirmModal.open}
        title={confirmModal.title}
        description={confirmModal.description}
        variant="danger"
        confirmText="Delete Workspace"
        onConfirm={confirmModal.onConfirm}
        onClose={() => setConfirmModal(prev => ({ ...prev, open: false }))}
        isLoading={deleteMutation.isPending}
      />
    </div>
  )
}
