import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useSharedWorkspaces, useAddWorkspaceMember, useRemoveWorkspaceMember } from '@/hooks/useSharedWorkspaces'
import { useAgents } from '@/hooks/useAgents'
import { Button } from '@/components/ui/Button'
import { ConfirmationModal } from '@/components/ui/ConfirmationModal'
import {
  ArrowLeft,
  Users,
  UserPlus,
  UserMinus,
  Crown,
  Loader2,
} from 'lucide-react'

export function SharedWorkspaceDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: workspaces = [], isLoading: wsLoading } = useSharedWorkspaces()
  const { data: agents = [] } = useAgents()
  const addMember = useAddWorkspaceMember()
  const removeMember = useRemoveWorkspaceMember()

  const [newMemberId, setNewMemberId] = useState('')
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

  const workspace = workspaces.find((w) => w.id === id)

  if (wsLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-base">
        <div className="w-12 h-12 border-4 border-accent-cyan/20 border-t-accent-cyan rounded-full animate-spin" />
      </div>
    )
  }

  if (!workspace) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-bg-base">
        <p className="text-text-secondary mb-4">Workspace not found</p>
        <Button variant="secondary" size="sm" onClick={() => navigate('/shared-workspaces')}>
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back
        </Button>
      </div>
    )
  }

  const owner = agents.find((a) => a.id === workspace.owner_id)
  const memberAgents = workspace.members
    .map((mid) => agents.find((a) => a.id === mid))
    .filter(Boolean)

  const availableAgents = agents.filter(
    (a) => a.id !== workspace.owner_id && !workspace.members.includes(a.id)
  )

  const handleAddMember = async () => {
    if (!newMemberId) return
    try {
      await addMember.mutateAsync({ workspaceId: workspace.id, memberId: newMemberId })
      setNewMemberId('')
    } catch (err) {
      alert('Failed to add member: ' + (err instanceof Error ? err.message : String(err)))
    }
  }

  const handleRemoveMember = async (memberId: string) => {
    const agent = agents.find(a => a.id === memberId)
    setConfirmModal({
      open: true,
      title: 'Remove Member',
      description: `Are you sure you want to remove ${agent?.name || memberId} from this workspace? They will no longer have access to the shared files.`,
      onConfirm: async () => {
        try {
          await removeMember.mutateAsync({ workspaceId: workspace.id, memberId })
        } catch (err) {
          alert('Failed to remove member: ' + (err instanceof Error ? err.message : String(err)))
        }
      },
    })
  }

  return (
    <div className="flex-1 overflow-y-auto bg-bg-base p-6 md:p-8">
      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <Button variant="ghost" size="sm" onClick={() => navigate('/shared-workspaces')}>
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <div>
          <h1 className="text-2xl font-display font-bold text-text-primary flex items-center gap-3">
            <Users className="w-8 h-8 text-accent-cyan" />
            {workspace.name}
          </h1>
          {workspace.description && (
            <p className="text-text-secondary mt-1">{workspace.description}</p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Info Card */}
        <div className="lg:col-span-1 space-y-6">
          <div className="bg-bg-surface border border-border-dim rounded-2xl p-5">
            <h2 className="text-sm font-display font-bold uppercase tracking-widest text-text-secondary mb-4">
              Details
            </h2>
            <div className="space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-text-secondary">ID</span>
                <span className="font-mono-data text-text-primary text-xs">{workspace.id}</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-text-secondary">Owner</span>
                <span className="font-mono-data text-text-primary text-xs">{owner?.name || workspace.owner_id}</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-text-secondary">Quota</span>
                <span className="font-mono-data text-text-primary text-xs">{(workspace.quota_bytes / 1024 / 1024).toFixed(0)} MB</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-text-secondary">Created</span>
                <span className="font-mono-data text-text-primary text-xs">
                  {new Date(workspace.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Members Card */}
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-bg-surface border border-border-dim rounded-2xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-display font-bold uppercase tracking-widest text-text-secondary">
                Members
              </h2>
              <span className="text-xs font-mono-data text-text-muted">
                {workspace.members.length + 1} total
              </span>
            </div>

            {/* Owner */}
            <div className="flex items-center gap-3 p-3 rounded-lg bg-bg-elevated border border-border-dim mb-3">
              <div className="w-8 h-8 rounded-lg bg-accent-amber/10 border border-accent-amber/30 flex items-center justify-center">
                <Crown className="w-4 h-4 text-accent-amber" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-text-primary truncate">
                  {owner?.name || workspace.owner_id}
                </p>
                <p className="text-[10px] font-mono-data text-text-muted truncate">
                  {workspace.owner_id}
                </p>
              </div>
              <span className="text-[10px] font-display uppercase tracking-wider text-accent-amber bg-accent-amber/10 px-2 py-1 rounded">
                Owner
              </span>
            </div>

            {/* Members list */}
            <div className="space-y-2">
              {memberAgents.map((agent) =>
                agent ? (
                  <div
                    key={agent.id}
                    className="flex items-center gap-3 p-3 rounded-lg border border-border-dim hover:bg-bg-elevated transition-colors"
                  >
                    <div className="w-8 h-8 rounded-lg bg-bg-elevated border border-border-dim flex items-center justify-center">
                      <Users className="w-4 h-4 text-text-muted" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-text-primary truncate">{agent.name}</p>
                      <p className="text-[10px] font-mono-data text-text-muted truncate">{agent.id}</p>
                    </div>
                    <button
                      onClick={() => handleRemoveMember(agent.id)}
                      className="p-2 rounded-lg bg-bg-elevated border border-border-dim text-accent-red transition-all hover:bg-accent-red hover:text-white"
                      title="Remove member"
                    >
                      <UserMinus className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ) : null
              )}
              {workspace.members.length === 0 && (
                <p className="text-sm text-text-muted text-center py-4">
                  No members yet.
                </p>
              )}
            </div>

            {/* Add member */}
            {availableAgents.length > 0 && (
              <div className="mt-4 pt-4 border-t border-border-dim flex items-center gap-3">
                <select
                  value={newMemberId}
                  onChange={(e) => setNewMemberId(e.target.value)}
                  className="flex-1 bg-bg-elevated border border-border-dim rounded-lg px-3 py-2 text-sm text-text-primary focus:border-accent-cyan focus:outline-none"
                >
                  <option value="">Select agent to add...</option>
                  {availableAgents.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleAddMember}
                  disabled={!newMemberId || addMember.isPending}
                >
                  {addMember.isPending ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <UserPlus className="w-4 h-4 mr-2" />
                  )}
                  Add
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>
      <ConfirmationModal
        open={confirmModal.open}
        title={confirmModal.title}
        description={confirmModal.description}
        variant="warning"
        confirmText="Remove Member"
        onConfirm={confirmModal.onConfirm}
        onClose={() => setConfirmModal(prev => ({ ...prev, open: false }))}
        isLoading={removeMember.isPending}
      />
    </div>
  )
}
