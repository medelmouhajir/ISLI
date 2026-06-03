import { useState, useEffect } from 'react'
import { AlertCircle, CheckCircle2, Terminal } from 'lucide-react'
import { cn } from '@/lib/utils'

interface CronBuilderProps {
  value: string | null
  onChange: (value: string | null) => void
  className?: string
}

const PRESETS = [
  { label: '5M_INTERVAL', value: '*/5 * * * *' },
  { label: 'HOURLY_SYNC', value: '0 * * * *' },
  { label: 'DAILY_0000', value: '0 0 * * *' },
  { label: 'WEEKLY_MON_0900', value: '0 9 * * 1' },
  { label: 'MONTHLY_01_0000', value: '0 0 1 * *' },
]

export function CronBuilder({ value, onChange, className }: CronBuilderProps) {
  const [inputValue, setInputValue] = useState(value || '')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setInputValue(value || '')
  }, [value])

  const validateCron = (cron: string) => {
    if (!cron) return null
    
    // Basic cron regex (5 fields)
    const cronRegex = /^(\*|([0-5]?\d)(-[0-5]?\d)?(,[0-5]?\d)*(\/[0-5]?\d)?)\s+(\*|([0-2]?\d)(-[0-2]?\d)?(,[0-2]?\d)*(\/[0-2]?\d)?)\s+(\*|(0?[1-9]|[12]\d|3[01])(-(0?[1-9]|[12]\d|3[01]))?(,(0?[1-9]|[12]\d|3[01]))*(\/(0?[1-9]|[12]\d|3[01]))?)\s+(\*|(0?[1-9]|1[012])(-(0?[1-9]|1[012]))?(,(0?[1-9]|1[012]))*(\/(0?[1-9]|1[012]))?)\s+(\*|([0-6])(-[0-6])?(,[0-6])*(\/[0-6])?)$/
    
    if (!cronRegex.test(cron)) {
      return 'SYNTAX_ERROR: INVALID_FIELD_COUNT'
    }

    // Check for high frequency (crude check)
    if ((cron.startsWith('*') && !cron.includes('/')) || (cron.startsWith('*/1') || cron.startsWith('*/2') || cron.startsWith('*/3') || cron.startsWith('*/4'))) {
        return 'RESOLUTION_ERROR: MIN_5M_REQUIRED'
    }

    return null
  }

  const handleInputChange = (val: string) => {
    setInputValue(val)
    const err = validateCron(val)
    setError(err)
    if (!err) {
      onChange(val || null)
    } else {
      onChange(null)
    }
  }

  return (
    <div className={cn('space-y-4 font-mono', className)}>
      <div className="flex items-center gap-2 mb-1 border-b border-zinc-800 pb-2">
        <Terminal className="w-3.5 h-3.5 text-zinc-500" />
        <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-400">
          Recurrence_Logic_Config
        </span>
      </div>

      <div className="relative">
        <input
          type="text"
          value={inputValue}
          onChange={(e) => handleInputChange(e.target.value)}
          placeholder="* * * * *"
          className={cn(
            'w-full bg-black border rounded-none px-3 py-2.5 text-sm font-mono focus:outline-none transition-all',
            error 
              ? 'border-accent-red/50 text-accent-red focus:border-accent-red' 
              : 'border-zinc-800 text-white focus:border-accent-cyan/50'
          )}
        />
        <div className="absolute right-3 top-3">
          {inputValue && !error ? (
            <CheckCircle2 className="w-4 h-4 text-[#C6FF4A]" />
          ) : error ? (
            <AlertCircle className="w-4 h-4 text-accent-red" />
          ) : null}
        </div>
      </div>

      {error && (
        <div className="bg-accent-red/10 border border-accent-red/20 px-2 py-1.5 flex items-center gap-2">
          <AlertCircle className="w-3 h-3 text-accent-red" />
          <p className="text-[9px] text-accent-red font-bold uppercase tracking-tight">
            {error}
          </p>
        </div>
      )}

      <div className="space-y-2">
        <span className="text-[9px] text-zinc-500 uppercase tracking-widest">Logic_Presets</span>
        <div className="flex flex-wrap gap-1.5">
          {PRESETS.map((p) => (
            <button
              key={p.value}
              type="button"
              onClick={() => handleInputChange(p.value)}
              className={cn(
                'px-2 py-1.5 rounded-none text-[9px] border transition-all uppercase tracking-tighter',
                inputValue === p.value
                  ? 'bg-accent-cyan text-black border-accent-cyan font-bold'
                  : 'bg-zinc-950 border-zinc-800 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200'
              )}
            >
              {p.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => handleInputChange('')}
            className="px-2 py-1.5 rounded-none text-[9px] border bg-zinc-950 border-zinc-800 text-zinc-500 hover:border-accent-red/30 hover:text-accent-red transition-all uppercase tracking-tighter"
          >
            Clear_Buffer
          </button>
        </div>
      </div>

      <div className="bg-zinc-950 border border-zinc-900 p-2 text-[9px] text-zinc-500 leading-tight">
        <p className="mb-1">PROTOCOL: STANDARD_5_FIELD_CRON</p>
        <p>SCHEMA: <span className="text-zinc-300">MIN HOUR DAY MONTH DOW</span></p>
        <p className="mt-1 text-accent-amber/70 font-bold">! WARNING: CRON_INTERVAL &lt; 300S WILL BE REJECTED</p>
      </div>
    </div>
  )
}
