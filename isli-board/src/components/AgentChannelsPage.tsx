import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useAgents, useUpdateAgent } from '@/hooks/useAgents'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { Label } from '@/components/ui/Label'
import { getChannelsJSON, postChannelsJSON, deleteChannelsJSON } from '@/lib/api'
import {
  ChevronLeft,
  Save,
  Radio,
  ShieldAlert,
  Calendar,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import QRCode from 'react-qr-code'

const CHANNEL_OPTIONS = ['telegram', 'whatsapp', 'email', 'web']

const ACCESS_MODE_OPTIONS = [
  { value: 'opt_in', label: 'Opt-In (default) — requires /start' },
  { value: 'open', label: 'Open — anyone can message' },
  { value: 'whitelist', label: 'Whitelist — approved numbers only' },
  { value: 'closed', label: 'Closed — single owner only' },
  { value: 'scheduled', label: 'Scheduled — time-window gated' },
]

const TIMEZONE_OPTIONS = [
  'UTC',
  'Africa/Casablanca',
  'America/New_York',
  'America/Los_Angeles',
  'America/Chicago',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Asia/Tokyo',
  'Asia/Dubai',
  'Asia/Singapore',
  'Australia/Sydney',
]

function WhatsAppConfig({ agentId }: { agentId: string }) {
  const [status, setStatus] = useState<string>('disconnected')
  const [qr, setQr] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fetchGenRef = useRef(0)

  const fetchStatus = useCallback(async () => {
    const gen = ++fetchGenRef.current
    try {
      const data = await getChannelsJSON<{ status: string }>(`/whatsapp/sessions/${agentId}/status`)
      if (gen !== fetchGenRef.current) return
      const normalized = data.status === 'closed' ? 'disconnected' : data.status
      setStatus(normalized)
      setError(null)
      if (normalized === 'open') setQr(null)
    } catch (err) {
      if (gen !== fetchGenRef.current) return
      setError(String(err))
    }
  }, [agentId])

  const fetchQr = useCallback(async () => {
    const gen = fetchGenRef.current
    try {
      const data = await getChannelsJSON<{ qr: string | null }>(`/whatsapp/sessions/${agentId}/qr`)
      if (gen !== fetchGenRef.current) return
      setQr(data.qr)
    } catch (err) {
      if (gen !== fetchGenRef.current) return
      setError(String(err))
    }
  }, [agentId])

  useEffect(() => {
    fetchStatus()
    const timer = setInterval(() => {
      if (status !== 'open') {
        fetchStatus()
        if (status === 'connecting') fetchQr()
      }
    }, 4000)
    return () => clearInterval(timer)
  }, [fetchStatus, fetchQr, status])

  const handleConnect = async () => {
    setLoading(true)
    setError(null)
    try {
      await postChannelsJSON(`/whatsapp/sessions/${agentId}`, {})
      await fetchStatus()
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }

  const handleDisconnect = async () => {
    setLoading(true)
    setError(null)
    try {
      await deleteChannelsJSON(`/whatsapp/sessions/${agentId}`)
      fetchGenRef.current++
      setStatus('disconnected')
      setQr(null)
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }

  const displayStatus = status === 'closed' ? 'disconnected' : status

  return (
    <div className="p-6 border border-border-bright bg-bg-surface space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={cn(
            "w-2 h-2 animate-pulse",
            displayStatus === 'open' ? "bg-accent-cyan shadow-glow-cyan" :
            displayStatus === 'connecting' ? "bg-accent-amber" : "bg-accent-red"
          )} />
          <span className="text-xs font-mono font-bold uppercase tracking-widest text-text-secondary">
            WHATSAPP_LINK: <span className={cn(
              displayStatus === 'open' ? "text-accent-cyan" :
              displayStatus === 'connecting' ? "text-accent-amber" : "text-accent-red"
            )}>{displayStatus.toUpperCase()}</span>
          </span>
        </div>
        <div className="flex gap-2">
          {displayStatus === 'disconnected' ? (
            <Button type="button" size="sm" onClick={handleConnect} disabled={loading} className="bg-bg-elevated border-border-bright text-text-primary hover:bg-bg-hover rounded-none h-8 px-4 text-[10px] tracking-widest">
              ESTABLISH_CONNECTION
            </Button>
          ) : (
            <Button type="button" size="sm" variant="ghost" onClick={handleDisconnect} disabled={loading} className="border-border-bright text-text-muted hover:text-text-primary rounded-none h-8 px-4 text-[10px] tracking-widest">
              TERMINATE
            </Button>
          )}
        </div>
      </div>

      {error && (
        <p className="text-[10px] text-accent-red font-mono uppercase tracking-wider">{error}</p>
      )}

      {displayStatus === 'connecting' && qr && (
        <div className="flex flex-col items-center gap-4 py-4 border-t border-border-dim">
          <div className="p-4 bg-white rounded-none">
            <QRCode value={qr} size={180} />
          </div>
          <p className="text-[10px] text-text-muted text-center max-w-[240px] uppercase tracking-widest leading-relaxed">
            SCAN_QR_CODE_VIA_WHATSAPP_TERMINAL_FOR_PAIRING
          </p>
        </div>
      )}

      {displayStatus === 'connecting' && !qr && (
        <div className="flex justify-center py-8 border-t border-border-dim">
          <div className="flex flex-col items-center gap-3">
            <div className="w-6 h-6 border border-border-bright border-t-accent-cyan animate-spin" />
            <span className="text-[10px] text-text-muted uppercase tracking-[0.2em]">AWAITING_BUFFER...</span>
          </div>
        </div>
      )}
    </div>
  )
}

export function AgentChannelsPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: agents = [], isLoading } = useAgents()
  const updateAgent = useUpdateAgent()

  const agent = useMemo(() => agents.find((a) => a.id === id), [agents, id])

  const [form, setForm] = useState<Record<string, any>>({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (agent) {
      const config = agent.config || {}
      const schedule = (config.whatsapp_schedule || {}) as Record<string, any>
      const windows = (schedule.windows || []) as any[]
      const firstWindow = windows[0] || {}

      setForm({
        channels: [...agent.channels],
        telegram_bot_token: config.telegram_bot_token || '',
        whatsapp_access_mode: config.whatsapp_access_mode || 'opt_in',
        whatsapp_allowed_user_id: config.whatsapp_allowed_user_id || '',
        whatsapp_allowed_jids: ((config.whatsapp_allowed_jids || []) as string[]).join('\n'),
        whatsapp_open_rate_limit_max: (config.whatsapp_open_rate_limit as any)?.max_msgs ?? 20,
        whatsapp_open_rate_limit_window: (config.whatsapp_open_rate_limit as any)?.window_seconds ?? 3600,
        whatsapp_schedule_timezone: schedule.timezone || 'UTC',
        whatsapp_schedule_days: (firstWindow.days || []) as number[],
        whatsapp_schedule_from: firstWindow.from || '09:00',
        whatsapp_schedule_to: firstWindow.to || '18:00',
        whatsapp_schedule_off_hours: schedule.off_hours_reply || '',
      })
    }
  }, [agent])

  const setField = useCallback((key: string, value: any) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }, [])

  const toggleChannel = useCallback((ch: string) => {
    setForm((prev) => {
      const current = (prev.channels as string[]) || []
      const next = current.includes(ch)
        ? current.filter((c) => c !== ch)
        : [...current, ch]
      return { ...prev, channels: next }
    })
  }, [])

  const dirty = useMemo(() => {
    if (!agent) return false
    const originalChannels = agent.channels
    const currentChannels = form.channels || []
    if (currentChannels.length !== originalChannels.length) return true
    if ([...currentChannels].sort().some((c, i) => c !== [...originalChannels].sort()[i])) return true

    const cfg = agent.config || {}
    if (form.telegram_bot_token !== (cfg.telegram_bot_token || '')) return true
    if (form.whatsapp_access_mode !== (cfg.whatsapp_access_mode || 'opt_in')) return true
    if (form.whatsapp_allowed_user_id !== (cfg.whatsapp_allowed_user_id || '')) return true
    const currentJids = String(form.whatsapp_allowed_jids || '').trim()
    const originalJids = ((cfg.whatsapp_allowed_jids || []) as string[]).join('\n')
    if (currentJids !== originalJids) return true

    const currentRl = cfg.whatsapp_open_rate_limit as any
    if (Number(form.whatsapp_open_rate_limit_max) !== (currentRl?.max_msgs ?? 20)) return true
    if (Number(form.whatsapp_open_rate_limit_window) !== (currentRl?.window_seconds ?? 3600)) return true

    const currentSchedule = cfg.whatsapp_schedule as any
    const currentWindows = (currentSchedule?.windows || []) as any[]
    const firstCurrentWindow = currentWindows[0] || {}
    if (form.whatsapp_schedule_timezone !== (currentSchedule?.timezone || 'UTC')) return true
    const currentDays = [...((form.whatsapp_schedule_days || []) as number[])].sort((a, b) => a - b)
    const originalDays = [...((firstCurrentWindow.days || []) as number[])].sort((a, b) => a - b)
    if (currentDays.length !== originalDays.length || currentDays.some((d, i) => d !== originalDays[i])) return true
    if (form.whatsapp_schedule_from !== (firstCurrentWindow.from || '09:00')) return true
    if (form.whatsapp_schedule_to !== (firstCurrentWindow.to || '18:00')) return true
    if (form.whatsapp_schedule_off_hours !== (currentSchedule?.off_hours_reply || '')) return true

    return false
  }, [form, agent])

  const resetForm = useCallback(() => {
    if (!agent) return
    const config = agent.config || {}
    const schedule = (config.whatsapp_schedule || {}) as Record<string, any>
    const windows = (schedule.windows || []) as any[]
    const firstWindow = windows[0] || {}

    setForm({
      channels: [...agent.channels],
      telegram_bot_token: config.telegram_bot_token || '',
      whatsapp_access_mode: config.whatsapp_access_mode || 'opt_in',
      whatsapp_allowed_user_id: config.whatsapp_allowed_user_id || '',
      whatsapp_allowed_jids: ((config.whatsapp_allowed_jids || []) as string[]).join('\n'),
      whatsapp_open_rate_limit_max: (config.whatsapp_open_rate_limit as any)?.max_msgs ?? 20,
      whatsapp_open_rate_limit_window: (config.whatsapp_open_rate_limit as any)?.window_seconds ?? 3600,
      whatsapp_schedule_timezone: schedule.timezone || 'UTC',
      whatsapp_schedule_days: (firstWindow.days || []) as number[],
      whatsapp_schedule_from: firstWindow.from || '09:00',
      whatsapp_schedule_to: firstWindow.to || '18:00',
      whatsapp_schedule_off_hours: schedule.off_hours_reply || '',
    })
  }, [agent])

  const handleSave = async () => {
    if (!agent) return
    setSaving(true)
    const payload: any = {
      channels: form.channels,
    }
    const config = { ...agent.config }

    if (form.telegram_bot_token) config.telegram_bot_token = form.telegram_bot_token
    else delete config.telegram_bot_token

    const mode = form.whatsapp_access_mode
    config.whatsapp_access_mode = mode

    if (mode === 'closed') {
      config.whatsapp_allowed_user_id = form.whatsapp_allowed_user_id.trim() || undefined
      delete config.whatsapp_allowed_jids
    } else if (mode === 'whitelist') {
      const rawJids = form.whatsapp_allowed_jids.trim()
      config.whatsapp_allowed_jids = rawJids ? rawJids.split(/\n|,/ ).map((j: string) => j.trim()).filter(Boolean) : []
      delete config.whatsapp_allowed_user_id
    } else {
      delete config.whatsapp_allowed_user_id
      delete config.whatsapp_allowed_jids
    }

    if (mode === 'open') {
      config.whatsapp_open_rate_limit = {
        max_msgs: Number(form.whatsapp_open_rate_limit_max),
        window_seconds: Number(form.whatsapp_open_rate_limit_window),
      }
    } else {
      delete config.whatsapp_open_rate_limit
    }

    if (mode === 'scheduled') {
      config.whatsapp_schedule = {
        timezone: form.whatsapp_schedule_timezone,
        windows: [{
          days: form.whatsapp_schedule_days.length > 0 ? form.whatsapp_schedule_days : [1, 2, 3, 4, 5],
          from: form.whatsapp_schedule_from,
          to: form.whatsapp_schedule_to,
        }],
        off_hours_reply: form.whatsapp_schedule_off_hours.trim() || undefined,
      }
    } else {
      delete config.whatsapp_schedule
    }

    payload.config = config

    updateAgent.mutate({ id: agent.id, payload }, {
      onSettled: () => setSaving(false)
    })
  }

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-base">
        <div className="w-8 h-8 border border-border-bright border-t-accent-cyan animate-spin" />
      </div>
    )
  }

  if (!agent) return null

  return (
    <div className="flex-1 bg-bg-base flex flex-col font-mono overflow-hidden">
      {/* Top Header */}
      <div className="h-12 border-b border-border-dim flex items-center justify-between px-6 bg-bg-base">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate(`/agents/${id}`)}
            className="text-text-secondary hover:text-text-primary transition-colors flex items-center gap-2 text-xs tracking-widest"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
            AGENT_ROOT
          </button>
          <div className="h-4 w-px bg-border-dim" />
          <h1 className="text-xs tracking-[0.3em] font-bold text-text-secondary">COMM_CHANNELS_v2.0</h1>
        </div>
        <div className="flex items-center gap-3">
           <span className="text-[10px] text-text-muted tabular-nums uppercase">NODE:{agent.name.toUpperCase()}</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 md:p-12">
        <div className="max-w-4xl mx-auto space-y-12">
          {/* Channel Selection */}
          <section className="space-y-6">
            <div className="space-y-2">
              <h2 className="text-xl font-bold tracking-tight text-text-primary flex items-center gap-3">
                <Radio className="w-5 h-5 text-accent-cyan" />
                01 // PROTOCOL_SELECTION
              </h2>
              <p className="text-text-secondary text-sm">Select active communication protocols for the autonomous unit.</p>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {CHANNEL_OPTIONS.map((ch) => {
                const active = form.channels?.includes(ch)
                return (
                  <button
                    key={ch}
                    onClick={() => toggleChannel(ch)}
                    className={cn(
                      "p-4 border text-left transition-all duration-300 relative group overflow-hidden",
                      active
                        ? "border-accent-cyan bg-accent-cyan/5"
                        : "border-border-bright bg-bg-surface hover:border-border-bright"
                    )}
                  >
                    <div className="flex flex-col gap-1 relative z-10">
                      <span className={cn(
                        "text-[9px] tracking-widest font-bold",
                        active ? "text-accent-cyan" : "text-text-muted"
                      )}>
                        STATUS: {active ? 'ACTIVE' : 'INACTIVE'}
                      </span>
                      <span className={cn(
                        "text-sm font-bold tracking-widest uppercase",
                        active ? "text-text-primary" : "text-text-secondary"
                      )}>
                        {ch}
                      </span>
                    </div>
                    {active && (
                      <div className="absolute top-0 right-0 p-2">
                         <div className="w-1.5 h-1.5 bg-accent-cyan" />
                      </div>
                    )}
                  </button>
                )
              })}
            </div>
          </section>

          {/* Protocol Configuration */}
          {(form.channels?.includes('telegram') || form.channels?.includes('whatsapp')) && (
            <section className="space-y-8 pt-8 border-t border-border-dim">
               <div className="space-y-2">
                <h2 className="text-xl font-bold tracking-tight text-text-primary flex items-center gap-3">
                  <ShieldAlert className="w-5 h-5 text-accent-cyan" />
                  02 // PROTOCOL_CONFIG
                </h2>
                <p className="text-text-secondary text-sm">Fine-tune protocol-specific operational parameters.</p>
              </div>

              <div className="space-y-10">
                {/* Telegram */}
                {form.channels?.includes('telegram') && (
                  <div className="space-y-4 animate-in fade-in slide-in-from-left-4 duration-500">
                    <div className="flex items-center gap-2">
                      <div className="w-1 h-4 bg-accent-cyan" />
                      <span className="text-xs font-bold tracking-widest text-text-primary">TELEGRAM_GATEWAY</span>
                    </div>
                    <div className="p-6 border border-border-bright bg-bg-surface space-y-4">
                       <div className="space-y-1.5">
                        <Label className="text-[10px] tracking-widest text-text-muted uppercase">Bot Authorization Token</Label>
                        <Input
                          value={form.telegram_bot_token}
                          onChange={(e) => setField('telegram_bot_token', e.target.value)}
                          placeholder="0000000000:AAHH..."
                          className="bg-bg-surface border-border-bright focus:border-accent-cyan text-text-primary rounded-none h-11"
                        />
                       </div>
                    </div>
                  </div>
                )}

                {/* WhatsApp */}
                {form.channels?.includes('whatsapp') && (
                  <div className="space-y-6 animate-in fade-in slide-in-from-left-4 duration-500">
                    <div className="flex items-center gap-2">
                      <div className="w-1 h-4 bg-accent-cyan" />
                      <span className="text-xs font-bold tracking-widest text-text-primary">WHATSAPP_GATEWAY</span>
                    </div>

                    <WhatsAppConfig agentId={id!} />

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 p-6 border border-border-bright bg-bg-surface">
                      <div className="space-y-4">
                        <div className="space-y-1.5">
                          <Label className="text-[10px] tracking-widest text-text-muted uppercase">Access Control Mode</Label>
                          <Select
                            value={form.whatsapp_access_mode}
                            onChange={(e) => setField('whatsapp_access_mode', e.target.value)}
                            className="bg-bg-surface border-border-bright focus:border-accent-cyan text-text-primary rounded-none h-11"
                          >
                            {ACCESS_MODE_OPTIONS.map((opt) => (
                              <option key={opt.value} value={opt.value}>{opt.label.toUpperCase()}</option>
                            ))}
                          </Select>
                        </div>

                        {form.whatsapp_access_mode === 'open' && (
                           <div className="grid grid-cols-2 gap-4 pt-2">
                              <div className="space-y-1.5">
                                <Label className="text-[10px] tracking-widest text-text-muted uppercase">Burst Max</Label>
                                <Input
                                  type="number"
                                  value={form.whatsapp_open_rate_limit_max}
                                  onChange={(e) => setField('whatsapp_open_rate_limit_max', e.target.value)}
                                  className="bg-bg-surface border-border-bright focus:border-accent-cyan text-text-primary rounded-none h-11"
                                />
                              </div>
                              <div className="space-y-1.5">
                                <Label className="text-[10px] tracking-widest text-text-muted uppercase">Window (Sec)</Label>
                                <Input
                                  type="number"
                                  value={form.whatsapp_open_rate_limit_window}
                                  onChange={(e) => setField('whatsapp_open_rate_limit_window', e.target.value)}
                                  className="bg-bg-surface border-border-bright focus:border-accent-cyan text-text-primary rounded-none h-11"
                                />
                              </div>
                           </div>
                        )}

                        {form.whatsapp_access_mode === 'whitelist' && (
                           <div className="space-y-1.5">
                              <Label className="text-[10px] tracking-widest text-text-muted uppercase">Allowed Identifiers (JIDs)</Label>
                              <Textarea
                                value={form.whatsapp_allowed_jids}
                                onChange={(e) => setField('whatsapp_allowed_jids', e.target.value)}
                                rows={6}
                                className="bg-bg-surface border-border-bright focus:border-accent-cyan text-text-primary rounded-none resize-none font-mono text-[10px] leading-relaxed p-4"
                                placeholder="2126XXXXXXXXX\n..."
                              />
                           </div>
                        )}

                        {form.whatsapp_access_mode === 'closed' && (
                           <div className="space-y-1.5">
                              <Label className="text-[10px] tracking-widest text-text-muted uppercase">Owner Identifier</Label>
                              <Input
                                value={form.whatsapp_allowed_user_id}
                                onChange={(e) => setField('whatsapp_allowed_user_id', e.target.value)}
                                className="bg-bg-surface border-border-bright focus:border-accent-cyan text-text-primary rounded-none h-11"
                                placeholder="2126XXXXXXXXX"
                              />
                           </div>
                        )}
                      </div>

                      <div className="space-y-4">
                        {form.whatsapp_access_mode === 'scheduled' ? (
                          <div className="space-y-4 animate-in fade-in duration-500">
                             <div className="space-y-1.5">
                                <Label className="text-[10px] tracking-widest text-text-muted uppercase">Timezone Registry</Label>
                                <Select
                                  value={form.whatsapp_schedule_timezone}
                                  onChange={(e) => setField('whatsapp_schedule_timezone', e.target.value)}
                                  className="bg-bg-surface border-border-bright focus:border-accent-cyan text-text-primary rounded-none h-11"
                                >
                                  {TIMEZONE_OPTIONS.map((tz) => (
                                    <option key={tz} value={tz}>{tz.toUpperCase()}</option>
                                  ))}
                                </Select>
                             </div>

                             <div className="space-y-1.5">
                                <Label className="text-[10px] tracking-widest text-text-muted uppercase">Duty Cycle (Days)</Label>
                                <div className="flex flex-wrap gap-2">
                                  {[1, 2, 3, 4, 5, 6, 7].map((day) => {
                                    const labels = ['', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
                                    const selected = form.whatsapp_schedule_days?.includes(day)
                                    return (
                                      <button
                                        key={day}
                                        onClick={() => {
                                          const next = selected
                                            ? form.whatsapp_schedule_days.filter((d: number) => d !== day)
                                            : [...form.whatsapp_schedule_days, day].sort((a,b) => a-b)
                                          setField('whatsapp_schedule_days', next)
                                        }}
                                        className={cn(
                                          "w-10 h-10 border text-[9px] font-bold tracking-widest transition-all",
                                          selected
                                            ? "border-accent-cyan bg-accent-cyan/10 text-text-primary"
                                            : "border-border-bright bg-bg-elevated text-text-muted hover:border-border-bright"
                                        )}
                                      >
                                        {labels[day]}
                                      </button>
                                    )
                                  })}
                                </div>
                             </div>

                             <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-1.5">
                                  <Label className="text-[10px] tracking-widest text-text-muted uppercase">Shift Start</Label>
                                  <Input
                                    type="time"
                                    value={form.whatsapp_schedule_from}
                                    onChange={(e) => setField('whatsapp_schedule_from', e.target.value)}
                                    className="bg-bg-surface border-border-bright focus:border-accent-cyan text-text-primary rounded-none h-11"
                                  />
                                </div>
                                <div className="space-y-1.5">
                                  <Label className="text-[10px] tracking-widest text-text-muted uppercase">Shift End</Label>
                                  <Input
                                    type="time"
                                    value={form.whatsapp_schedule_to}
                                    onChange={(e) => setField('whatsapp_schedule_to', e.target.value)}
                                    className="bg-bg-surface border-border-bright focus:border-accent-cyan text-text-primary rounded-none h-11"
                                  />
                                </div>
                             </div>
                             <div className="space-y-1.5">
                                <Label className="text-[10px] tracking-widest text-text-muted uppercase">Off-Hours Reply</Label>
                                <Textarea
                                  value={form.whatsapp_schedule_off_hours}
                                  onChange={(e) => setField('whatsapp_schedule_off_hours', e.target.value)}
                                  rows={3}
                                  className="bg-bg-surface border-border-bright focus:border-accent-cyan text-text-primary rounded-none resize-none font-mono text-[10px] leading-relaxed p-4"
                                  placeholder="This assistant is currently offline..."
                                />
                             </div>
                          </div>
                        ) : (
                          <div className="h-full flex flex-col items-center justify-center p-6 border border-dashed border-border-bright opacity-20">
                             <Calendar className="w-8 h-8 mb-2" />
                             <span className="text-[9px] tracking-widest">SCHEDULE_MOD_INACTIVE</span>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </section>
          )}

          {/* Persistent Footer Stats/Actions */}
          <div className="h-24" /> {/* Spacer */}
        </div>
      </div>

      {/* Floating Action Bar */}
      {dirty && (
        <div className="h-20 border-t border-border-dim bg-bg-base/90 backdrop-blur-md flex items-center justify-between px-12 animate-in slide-in-from-bottom-full duration-500">
          <div className="flex flex-col">
            <span className="text-[10px] text-accent-cyan tracking-[0.2em] font-bold">PENDING_MODIFICATIONS_DETECTED</span>
            <span className="text-[10px] text-text-muted uppercase">Commit changes to apply protocol updates</span>
          </div>
          <div className="flex gap-4">
            <Button
              variant="ghost"
              onClick={resetForm}
              className="text-text-muted hover:text-text-primary rounded-none border-border-bright px-8 h-11 text-xs tracking-widest"
            >
              DISCARD
            </Button>
            <Button
              onClick={handleSave}
              disabled={saving}
              className="bg-accent-cyan text-black hover:opacity-90 rounded-none px-10 h-11 font-bold text-xs tracking-[0.2em]"
            >
              {saving ? 'SYNCHRONIZING...' : 'COMMIT_UPDATES'}
              <Save className="ml-3 w-4 h-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Footer Info */}
      <div className="h-10 border-t border-border-dim bg-bg-base flex items-center justify-between px-6">
         <div className="flex items-center gap-6">
            <span className="text-[9px] text-text-muted tracking-[0.2em]">PROTOCOL_REV: 2.1.0</span>
            <span className="text-[9px] text-text-muted tracking-[0.2em]">GATEWAY_NODES: 4</span>
         </div>
         <span className="text-[9px] text-text-muted tracking-[0.2em] uppercase tabular-nums">SECURE_LINK_ESTABLISHED</span>
      </div>
    </div>
  )
}
