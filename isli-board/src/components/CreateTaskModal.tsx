import { useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Select } from '@/components/ui/Select'
import { Button } from '@/components/ui/Button'
import { CronBuilder } from '@/components/CronBuilder'
import { postJSON } from '@/lib/api'
import type { Agent } from '@/types'
import { FilePlus, Calendar, Info } from 'lucide-react'
import { cn } from '@/lib/utils'

interface CreateTaskModalProps {
  open: boolean
  onClose: () => void
  agents: Agent[]
  onAuthRequired?: () => void
}

type ScheduleType = 'onetime' | 'recurring'

export function CreateTaskModal({ open, onClose, agents, onAuthRequired }: CreateTaskModalProps) {
  const [loading, setLoading] = useState(false)
  const [scheduleType, setScheduleType] = useState<ScheduleType>('onetime')
  const [cronExpression, setCronExpression] = useState<string | null>(null)

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
        scheduled_at: scheduleType === 'onetime' && scheduledAtRaw ? new Date(scheduledAtRaw).toISOString() : null,
        cron_expression: scheduleType === 'recurring' ? cronExpression : null,
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
    <Modal open={open} onClose={onClose} title="" className="max-w-md bg-black border-zinc-800">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-8 h-8 rounded-none bg-accent-cyan/10 flex items-center justify-center border border-accent-cyan/20">
          <FilePlus className="w-4 h-4 text-accent-cyan" />
        </div>
        <div>
          <h2 className="text-sm font-mono font-bold uppercase tracking-[0.2em] text-white">Init_Task_Sequence</h2>
          <p className="text-[10px] font-mono text-text-muted">MANUAL_ENTRY_V1.0</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        <div className="space-y-1.5">
          <label className="text-[10px] font-mono uppercase tracking-widest text-text-secondary flex items-center gap-2">
            <span className="w-1 h-1 bg-accent-cyan" /> Task_Label
          </label>
          <Input 
            name="title" 
            placeholder="PRIMARY_IDENTIFIER" 
            required 
            className="bg-zinc-950 border-zinc-800 font-mono text-sm rounded-none focus:border-accent-cyan/50"
          />
        </div>

        <div className="space-y-1.5">
          <label className="text-[10px] font-mono uppercase tracking-widest text-text-secondary flex items-center gap-2">
            <span className="w-1 h-1 bg-zinc-600" /> Instructions_Data
          </label>
          <Textarea 
            name="description" 
            placeholder="DETAILED_EXECUTION_PARAMETERS" 
            rows={3} 
            className="bg-zinc-950 border-zinc-800 font-mono text-sm rounded-none focus:border-accent-cyan/50 resize-none"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label className="text-[10px] font-mono uppercase tracking-widest text-text-secondary flex items-center gap-2">
              <span className="w-1 h-1 bg-accent-cyan" /> Assign_Unit
            </label>
            <Select name="agent_id" className="bg-zinc-950 border-zinc-800 font-mono text-xs rounded-none">
              <option value="">STANDALONE_BUS</option>
              {agents.map((a) => (
                <option key={a.id} value={a.id}>{a.name.toUpperCase()}</option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5">
            <label className="text-[10px] font-mono uppercase tracking-widest text-text-secondary flex items-center gap-2">
              <span className="w-1 h-1 bg-accent-amber" /> Priority_Tier
            </label>
            <Input 
              name="priority" 
              type="number" 
              min={1} 
              max={5} 
              defaultValue={3} 
              className="bg-zinc-950 border-zinc-800 font-mono text-sm rounded-none"
            />
          </div>
        </div>

        <div className="border border-zinc-800 p-4 space-y-4 bg-zinc-950/50">
          <div className="flex items-center justify-between">
            <label className="text-[10px] font-mono uppercase tracking-widest text-text-secondary flex items-center gap-2">
              <span className="w-1.5 h-1.5 bg-accent-amber animate-pulse" /> Scheduling_Matrix
            </label>
            <div className="flex border border-zinc-800 p-0.5">
              <button
                type="button"
                onClick={() => setScheduleType('onetime')}
                className={cn(
                  "px-2 py-1 text-[9px] font-mono uppercase tracking-tighter transition-all",
                  scheduleType === 'onetime' ? "bg-accent-amber text-black font-bold" : "text-text-muted hover:text-text-secondary"
                )}
              >
                Onetime
              </button>
              <button
                type="button"
                onClick={() => setScheduleType('recurring')}
                className={cn(
                  "px-2 py-1 text-[9px] font-mono uppercase tracking-tighter transition-all",
                  scheduleType === 'recurring' ? "bg-accent-cyan text-black font-bold" : "text-text-muted hover:text-text-secondary"
                )}
              >
                Recurring
              </button>
            </div>
          </div>

          {scheduleType === 'onetime' ? (
            <div className="space-y-1.5 animate-in fade-in duration-300">
              <div className="relative">
                <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-accent-amber" />
                <Input 
                  name="scheduled_at" 
                  type="datetime-local" 
                  className="bg-black border-zinc-800 pl-10 font-mono text-xs rounded-none h-9"
                />
              </div>
            </div>
          ) : (
            <div className="animate-in fade-in duration-300">
              <CronBuilder 
                value={cronExpression} 
                onChange={setCronExpression}
                className="bg-black border border-zinc-800 p-3 rounded-none"
              />
            </div>
          )}

          {/* Differentiator: The Signal Ticker */}
          <div className="bg-black border-t border-zinc-800 -mx-4 -mb-4 px-4 py-2 flex items-center gap-3 overflow-hidden">
            <div className="shrink-0 flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-[#C6FF4A] shadow-[0_0_8px_#C6FF4A]" />
              <span className="text-[9px] font-mono font-bold text-[#C6FF4A] uppercase tracking-widest">Signal_Live</span>
            </div>
            <div className="flex-1 whitespace-nowrap overflow-hidden">
              <div className="inline-block animate-marquee font-mono text-[9px] text-[#C6FF4A]/80 tracking-tight">
                {scheduleType === 'recurring' && cronExpression 
                  ? `RECURRENCE_ACTIVE_ON_BUS: [${cronExpression}] -- WAITING_FOR_NEXT_TICK -- ID: ${Math.random().toString(36).substring(7).toUpperCase()}`
                  : scheduleType === 'onetime' 
                    ? `ISO_SCHEDULE_READY -- PENDING_USER_CONFIRMATION -- STATUS: READY_TO_BROADCAST`
                    : `SCHEDULING_ENGINE_IDLE -- WAITING_FOR_INPUT_DATA`}
              </div>
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-2">
          <div className="flex items-center gap-2 text-[9px] font-mono text-text-muted">
            <Info className="w-3 h-3" />
            <span>ENFORCE_TASK_BUDGET: ACTIVE</span>
          </div>
          <div className="flex gap-2">
            <Button 
              type="button" 
              variant="ghost" 
              onClick={onClose} 
              disabled={loading}
              className="font-mono text-[10px] uppercase tracking-widest rounded-none border border-transparent hover:border-zinc-800"
            >
              Abort
            </Button>
            <Button 
              type="submit" 
              variant="primary" 
              disabled={loading || (scheduleType === 'recurring' && !cronExpression)}
              className="bg-accent-cyan hover:bg-accent-cyan/90 text-black font-mono text-[10px] font-bold uppercase tracking-[0.2em] rounded-none px-6"
            >
              Execute_Init
            </Button>
          </div>
        </div>
      </form>
    </Modal>
  )
}
