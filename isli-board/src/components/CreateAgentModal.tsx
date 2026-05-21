import { useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { postJSON } from '@/lib/api'
import { UserPlus } from 'lucide-react'

interface CreateAgentModalProps {
  open: boolean
  onClose: () => void
  onCreated: () => void
  onAuthRequired: () => void
}

export function CreateAgentModal({ open, onClose, onCreated, onAuthRequired }: CreateAgentModalProps) {
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setLoading(true)
    const fd = new FormData(e.currentTarget)
    try {
      await postJSON('/v1/agents', {
        id: fd.get('id') || undefined,
        name: fd.get('name'),
        description: fd.get('description'),
        persona: fd.get('persona'),
        model_provider: fd.get('model_provider'),
        model_id: fd.get('model_id'),
        token_budget: fd.get('token_budget') ? Number(fd.get('token_budget')) : null,
      })
      onCreated()
      onClose()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : ''
      if (msg.includes('401') || msg.includes('403')) {
        onAuthRequired()
      }
      console.error('Failed to create agent:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Create Agent">
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="space-y-1">
          <label className="text-xs font-display uppercase tracking-wider text-text-secondary">Agent ID <span className="text-text-muted normal-case">(optional)</span></label>
          <Input name="id" placeholder="agent-001" />
        </div>

        <div className="space-y-1">
          <label className="text-xs font-display uppercase tracking-wider text-text-secondary">Name</label>
          <Input name="name" placeholder="Agent name" required />
        </div>

        <div className="space-y-1">
          <label className="text-xs font-display uppercase tracking-wider text-text-secondary">Description</label>
          <Input name="description" placeholder="What does this agent do?" />
        </div>

        <div className="space-y-1">
          <label className="text-xs font-display uppercase tracking-wider text-text-secondary">Persona</label>
          <textarea
            name="persona"
            placeholder="Agent's tone, role, and instructions..."
            rows={4}
            className="w-full bg-bg-base/50 border border-border-dim rounded-xl px-4 py-3 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-cyan transition-all resize-none font-sans"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-xs font-display uppercase tracking-wider text-text-secondary">Provider</label>
            <Input name="model_provider" placeholder="anthropic" />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-display uppercase tracking-wider text-text-secondary">Model ID</label>
            <Input name="model_id" placeholder="claude-sonnet-4-6" />
          </div>
        </div>

        <div className="space-y-1">
          <label className="text-xs font-display uppercase tracking-wider text-text-secondary">Token Budget</label>
          <Input name="token_budget" type="number" placeholder="100000" />
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose} disabled={loading}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={loading}>
            <UserPlus className="w-3.5 h-3.5 mr-1.5" />
            Create
          </Button>
        </div>
      </form>
    </Modal>
  )
}
