import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getJSON, postJSON, deleteJSON } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Label } from '@/components/ui/Label'
import { ConfirmationModal } from '@/components/ui/ConfirmationModal'
import { ChevronLeft, KeyRound, Plus, Trash2, Eye, EyeOff, Shield } from 'lucide-react'
import { cn } from '@/lib/utils'

interface Secret {
  name: string
  description: string | null
  created_at: string | null
  updated_at: string | null
}

export function AgentSecretsPage() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newValue, setNewValue] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [showValue, setShowValue] = useState(false)
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

  const { data: secrets = [], isLoading } = useQuery({
    queryKey: ['secrets', id],
    queryFn: () => getJSON<Secret[]>(`/v1/secrets?agent_id=${id}`),
    enabled: !!id,
    staleTime: 30000,
  })

  const createMutation = useMutation({
    mutationFn: () =>
      postJSON('/v1/secrets', {
        agent_id: id,
        name: newName.trim(),
        value: newValue,
        description: newDescription.trim() || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['secrets', id] })
      setShowCreate(false)
      setNewName('')
      setNewValue('')
      setNewDescription('')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (name: string) => deleteJSON(`/v1/secrets/${name}?agent_id=${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['secrets', id] })
    },
  })

  const handleCreate = () => {
    if (!newName.trim() || !newValue) return
    createMutation.mutate()
  }

  return (
    <div className="flex-1 overflow-y-auto bg-bg-base">
      <div className="p-6 md:p-8 max-w-4xl mx-auto space-y-8">
        {/* Header */}
        <div className="flex flex-col gap-4">
          <Link
            to={`/agents/${id}`}
            className="flex items-center gap-2 text-xs font-display font-bold uppercase tracking-widest text-text-muted hover:text-accent-cyan transition-colors w-fit"
          >
            <ChevronLeft className="w-4 h-4" />
            Back to Agent
          </Link>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-none bg-bg-surface border border-border-dim flex items-center justify-center text-accent-cyan">
                <Shield className="w-6 h-6" />
              </div>
              <div>
                <h1 className="text-xl font-display font-bold text-text-primary">Secrets Vault</h1>
                <p className="text-[10px] font-mono-data text-text-muted uppercase tracking-wider">
                  Agent: {id}
                </p>
              </div>
            </div>
            <Button
              type="button"
              onClick={() => setShowCreate((v) => !v)}
              className="bg-accent-cyan/10 hover:bg-accent-cyan/20 text-accent-cyan border-accent-cyan/20"
            >
              <Plus className="w-4 h-4 mr-2" />
              {showCreate ? 'Cancel' : 'Add Secret'}
            </Button>
          </div>
        </div>

        {/* Create Form */}
        {showCreate && (
          <div className="bg-bg-surface border border-border-dim rounded-none overflow-hidden shadow-sm animate-in fade-in slide-in-from-top-2 duration-200">
            <div className="px-6 py-4 border-b border-border-dim bg-bg-elevated/30">
              <h2 className="text-xs font-display font-bold uppercase tracking-widest text-text-secondary flex items-center gap-2">
                <KeyRound className="w-4 h-4 text-accent-cyan" />
                New Secret
              </h2>
            </div>
            <div className="p-6 space-y-4">
              <div className="space-y-2">
                <Label>Name</Label>
                <Input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="e.g., openai_api_key"
                  className="font-mono-data"
                />
              </div>
              <div className="space-y-2">
                <Label>Value</Label>
                <div className="relative">
                  <Input
                    type={showValue ? 'text' : 'password'}
                    value={newValue}
                    onChange={(e) => setNewValue(e.target.value)}
                    placeholder="Secret value"
                    className="pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowValue((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary transition-colors"
                  >
                    {showValue ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                  </button>
                </div>
              </div>
              <div className="space-y-2">
                <Label>Description</Label>
                <Textarea
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  placeholder="Optional description of what this secret is used for"
                  rows={2}
                  className="resize-none"
                />
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <Button type="button" variant="ghost" onClick={() => setShowCreate(false)}>
                  Discard
                </Button>
                <Button
                  type="button"
                  onClick={handleCreate}
                  disabled={createMutation.isPending || !newName.trim() || !newValue}
                >
                  {createMutation.isPending ? 'Saving...' : 'Save Secret'}
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Secrets List */}
        <div className="bg-bg-surface border border-border-dim rounded-none overflow-hidden shadow-sm">
          <div className="px-6 py-4 border-b border-border-dim bg-bg-elevated/30 flex items-center justify-between">
            <h2 className="text-xs font-display font-bold uppercase tracking-widest text-text-secondary flex items-center gap-2">
              <KeyRound className="w-4 h-4 text-accent-cyan" />
              Stored Secrets
            </h2>
            <span className="text-[10px] font-mono-data text-text-muted">
              {secrets.length} secret{secrets.length !== 1 ? 's' : ''}
            </span>
          </div>

          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-6 h-6 border-2 border-accent-cyan/20 border-t-accent-cyan rounded-none animate-spin" />
            </div>
          ) : secrets.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 px-6">
              <Shield className="w-12 h-12 text-text-muted mb-4 opacity-30" />
              <p className="text-sm text-text-secondary font-display">No secrets stored yet</p>
              <p className="text-xs text-text-muted mt-1 text-center max-w-sm">
                Secrets are encrypted at rest with AES-256-GCM. They are only accessible to this agent at runtime via the get_secret tool.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-border-dim/50">
              {secrets.map((secret) => (
                <div
                  key={secret.name}
                  className="px-6 py-4 flex items-start justify-between gap-4 hover:bg-bg-elevated/20 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <KeyRound className="w-3.5 h-3.5 text-accent-cyan shrink-0" />
                      <span className="text-sm font-mono-data font-bold text-text-primary truncate">
                        {secret.name}
                      </span>
                    </div>
                    {secret.description && (
                      <p className="text-xs text-text-muted ml-5.5">{secret.description}</p>
                    )}
                    <div className="flex items-center gap-3 mt-2 ml-5.5">
                      <span className="text-[10px] font-mono-data text-text-muted/60">
                        Updated: {secret.updated_at ? new Date(secret.updated_at).toLocaleString() : '—'}
                      </span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setConfirmModal({
                        open: true,
                        title: 'Delete Secret',
                        description: `Are you sure you want to delete secret "${secret.name}"? This action cannot be undone and any agents relying on this secret may fail.`,
                        onConfirm: () => deleteMutation.mutate(secret.name),
                      })
                    }}
                    disabled={deleteMutation.isPending}
                    className={cn(
                      'shrink-0 p-2 rounded-none border border-border-dim/50',
                      'text-text-muted hover:text-accent-red hover:border-accent-red/30 hover:bg-accent-red/5',
                      'transition-all active:scale-95'
                    )}
                    title="Delete secret"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      <ConfirmationModal
        open={confirmModal.open}
        title={confirmModal.title}
        description={confirmModal.description}
        variant="danger"
        confirmText="Delete Secret"
        onConfirm={confirmModal.onConfirm}
        onClose={() => setConfirmModal(prev => ({ ...prev, open: false }))}
        isLoading={deleteMutation.isPending}
      />
    </div>
  )
}
