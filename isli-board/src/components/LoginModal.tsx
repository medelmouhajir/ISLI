import { useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { useAuth } from '@/hooks/useAuth'
import { KeyRound } from 'lucide-react'

interface LoginModalProps {
  open: boolean
  onClose: () => void
}

export function LoginModal({ open, onClose }: LoginModalProps) {
  const { login } = useAuth()
  const [value, setValue] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = value.trim()
    if (!trimmed) {
      setError('API key is required')
      return
    }
    login(trimmed)
    setValue('')
    setError('')
    onClose()
  }

  return (
    <Modal open={open} onClose={onClose} title="Authenticate">
      <form onSubmit={handleSubmit} className="space-y-4">
        <p className="text-sm text-text-secondary">
          Enter the Admin API Key configured in isli-core to unlock admin operations such as creating agents.
        </p>
        <div className="space-y-1">
          <label className="text-xs font-display uppercase tracking-wider text-text-secondary">Admin API Key</label>
          <Input
            type="password"
            placeholder="isli-admin-dev-key"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            autoFocus
          />
        </div>
        {error && (
          <p className="text-xs text-accent-red">{error}</p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary">
            <KeyRound className="w-3.5 h-3.5 mr-1.5" />
            Log In
          </Button>
        </div>
      </form>
    </Modal>
  )
}
