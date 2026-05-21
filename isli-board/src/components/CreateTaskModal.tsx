import { useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Select } from '@/components/ui/Select'
import { Button } from '@/components/ui/Button'
import { postJSON } from '@/lib/api'
import type { Agent } from '@/types'
import { FilePlus } from 'lucide-react'

interface CreateTaskModalProps {
  open: boolean
  onClose: () => void
  agents: Agent[]
  onAuthRequired?: () => void
}

export function CreateTaskModal({ open, onClose, agents, onAuthRequired }: CreateTaskModalProps) {
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setLoading(true)
    const fd = new FormData(e.currentTarget)
    try {
      const scheduledAtRaw = fd.get('scheduled_at') as string
      await postJSON('/v1/tasks', {
        title: fd.get('title'),
        description: fd.get('description'),
        created_by: fd.get('created_by') || 'board',
        agent_id: fd.get('agent_id') || null,
        priority: Number(fd.get('priority') || 3),
        type: 'task',
        scheduled_at: scheduledAtRaw ? new Date(scheduledAtRaw).toISOString() : null,
      })
      onClose()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : ''
      if (msg.includes('401') || msg.includes('403')) {
        onAuthRequired?.()
      }
      console.error('Failed to create task:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Create Task">
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="space-y-1">
          <label className="text-xs font-display uppercase tracking-wider text-text-secondary">Title</label>
          <Input name="title" placeholder="Task title" required />
        </div>

        <div className="space-y-1">
          <label className="text-xs font-display uppercase tracking-wider text-text-secondary">Description</label>
          <Textarea name="description" placeholder="Task description" rows={3} />
        </div>

        <div className="space-y-1">
          <label className="text-xs font-display uppercase tracking-wider text-text-secondary">Assignee</label>
          <Select name="agent_id">
            <option value="">No agent</option>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </Select>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-xs font-display uppercase tracking-wider text-text-secondary">Created By</label>
            <Input name="created_by" placeholder="board" />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-display uppercase tracking-wider text-text-secondary">Priority</label>
            <Input name="priority" type="number" min={1} max={5} defaultValue={3} />
          </div>
        </div>

        <div className="space-y-1">
          <label className="text-xs font-display uppercase tracking-wider text-text-secondary">Scheduled For</label>
          <Input name="scheduled_at" type="datetime-local" />
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose} disabled={loading}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={loading}>
            <FilePlus className="w-3.5 h-3.5 mr-1.5" />
            Create
          </Button>
        </div>
      </form>
    </Modal>
  )
}
