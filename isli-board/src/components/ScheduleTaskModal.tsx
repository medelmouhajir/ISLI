import { useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { Calendar } from 'lucide-react'

interface ScheduleTaskModalProps {
  open: boolean
  onClose: () => void
  onSubmit: (date: string) => void
  taskTitle?: string
}

export function ScheduleTaskModal({ open, onClose, onSubmit, taskTitle }: ScheduleTaskModalProps) {
  const [date, setDate] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!date) return
    onSubmit(new Date(date).toISOString())
    onClose()
  }

  return (
    <Modal open={open} onClose={onClose} title="Schedule Task">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <p className="text-sm text-text-secondary">
            Set a scheduled time for: <span className="text-text-primary font-medium">{taskTitle}</span>
          </p>
          <div className="space-y-1">
            <label className="text-xs font-display uppercase tracking-wider text-text-secondary">
              Execution Time
            </label>
            <Input
              type="datetime-local"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              required
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={!date}>
            <Calendar className="w-3.5 h-3.5 mr-1.5" />
            Schedule
          </Button>
        </div>
      </form>
    </Modal>
  )
}
