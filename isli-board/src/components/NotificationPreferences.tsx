import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Bell,
  Save,
  Loader2,
  Info,
  Share,
  Smartphone,
  MessageSquare,
  Mail,
  BellRing,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useNotificationPreferences, useUpdateNotificationPreferences } from '@/hooks/useNotificationPreferences'
import { useWebPush } from '@/hooks/useWebPush'
import type { NotificationCategoryPreference, NotificationPreferences } from '@/types'

const CHANNEL_META: Record<string, { label: string; icon: React.ElementType }> = {
  in_app: { label: 'In-App', icon: Bell },
  web_push: { label: 'Web Push', icon: BellRing },
  telegram: { label: 'Telegram', icon: MessageSquare },
  whatsapp: { label: 'WhatsApp', icon: Smartphone },
  email: { label: 'Email', icon: Mail },
}

const CATEGORY_DESCRIPTIONS: Record<string, string> = {
  agent_crash: 'Agent stopped unexpectedly and recovery failed.',
  task_completed: 'A delegated task reaches the done column.',
  task_failed: 'A task moved to failed or was blocked.',
  task_assigned: 'A task is assigned to an agent.',
  session_message: 'New web chat or Council room messages while using the Board.',
  channel_message: 'New inbound messages from Telegram, WhatsApp, or Email.',
  agent_online: 'An agent comes back online.',
  agent_offline: 'An agent heartbeat goes stale.',
  memory_write: 'A memory fact is saved from a session.',
  workspace_update: 'A workspace file is modified.',
  task_created: 'A new task appears on the board.',
  system_digest: 'Periodic summary of lower-priority activity.',
}

export function NotificationPreferencesPage() {
  // TODO: replace with actual logged-in user ID once auth system matures
  const userId = 'admin'
  const { data: prefs, isLoading } = useNotificationPreferences(userId)
  const update = useUpdateNotificationPreferences(userId)
  const { isSupported, isSubscribed, isIOS, isStandalone, subscribe, unsubscribe } = useWebPush(userId)

  const [localPrefs, setLocalPrefs] = useState<NotificationPreferences | undefined>()
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  // Sync local state when server preferences load or refetch after save.
  useEffect(() => {
    if (prefs) {
      setLocalPrefs(prefs)
    }
  }, [prefs])

  if (isLoading || !prefs) {
    return (
      <div className="flex-1 overflow-y-auto bg-bg-base h-full w-full min-h-0 flex items-center justify-center">
        <Loader2 className="w-6 h-6 text-accent-cyan animate-spin" />
      </div>
    )
  }

  const categories = localPrefs?.categories ?? prefs.categories ?? {}

  const setCategoryEnabled = (key: string, enabled: boolean) => {
    const current = categories[key]
    if (!current) return
    const next: Record<string, NotificationCategoryPreference> = {
      ...categories,
      [key]: { ...current, enabled },
    }
    setLocalPrefs((p) => ({ ...(p ?? prefs), categories: next }))
  }

  const toggleChannel = (key: string, channel: string) => {
    const current = categories[key]
    if (!current) return
    const has = current.channels?.includes(channel) ?? false
    const nextChannels = has
      ? (current.channels ?? []).filter((c) => c !== channel)
      : [...(current.channels ?? []), channel]
    const next: Record<string, NotificationCategoryPreference> = {
      ...categories,
      [key]: { ...current, channels: nextChannels },
    }
    setLocalPrefs((p) => ({ ...(p ?? prefs), categories: next }))
  }

  return (
    <div className="flex-1 overflow-y-auto bg-bg-base h-full w-full min-h-0">
      <div className="p-6 md:p-8 max-w-3xl mx-auto">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-accent-cyan/10 border border-accent-cyan/20 flex items-center justify-center text-accent-cyan">
            <Bell className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-sm font-display font-bold text-text-primary uppercase tracking-wider">
              Notifications
            </h1>
            <p className="text-[10px] text-text-muted font-mono-data">
              Alert routing, quiet hours, and per-category preferences
            </p>
          </div>
        </div>

        <div className="space-y-6">
          {/* Web Push Toggle */}
          <div className="bg-bg-surface border border-border-dim rounded-xl p-5">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xs font-display font-bold uppercase tracking-wider text-text-primary">
                  Web Push Notifications
                </h3>
                <p className="text-[11px] text-text-secondary mt-1">
                  Receive alerts on this device even when the browser is closed
                </p>
                {isIOS && !isStandalone && (
                  <div className="mt-2 flex items-start gap-2 p-2 bg-accent-amber/10 border border-accent-amber/20 rounded-md">
                    <Info className="w-3.5 h-3.5 text-accent-amber shrink-0 mt-0.5" />
                    <p className="text-[10px] text-accent-amber font-medium">
                      iOS Support: Tap <Share className="w-3 h-3 inline mx-0.5" /> Share → "Add to Home Screen" first to enable notifications.
                    </p>
                  </div>
                )}
              </div>
              <button
                onClick={() => isSubscribed ? unsubscribe() : subscribe()}
                disabled={!isSupported || (isIOS && !isStandalone)}
                className={cn(
                  'relative w-11 h-6 rounded-none border transition-colors',
                  isSubscribed
                    ? 'bg-accent-cyan border-accent-cyan'
                    : 'bg-bg-elevated border-border-dim',
                  (!isSupported || (isIOS && !isStandalone)) && 'opacity-30 cursor-not-allowed'
                )}
              >
                <span
                  className={cn(
                    'absolute top-0.5 left-0.5 w-4.5 h-4.5 bg-white rounded-none transition-transform',
                    isSubscribed ? 'translate-x-5' : 'translate-x-0'
                  )}
                />
              </button>
            </div>
          </div>

          {/* Global toggle */}
          <div className="bg-bg-surface border border-border-dim rounded-xl p-5">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xs font-display font-bold uppercase tracking-wider text-text-primary">
                  Global Notifications
                </h3>
                <p className="text-[11px] text-text-secondary mt-1">
                  Master switch for all notification channels
                </p>
              </div>
              <button
                onClick={() => setLocalPrefs((p) => ({ ...(p ?? prefs), global_enabled: !(p?.global_enabled ?? prefs.global_enabled) }))}
                className={cn(
                  'relative w-11 h-6 rounded-none border transition-colors',
                  localPrefs?.global_enabled
                    ? 'bg-accent-cyan border-accent-cyan'
                    : 'bg-bg-elevated border-border-dim'
                )}
              >
                <span
                  className={cn(
                    'absolute top-0.5 left-0.5 w-4.5 h-4.5 bg-white rounded-none transition-transform',
                    localPrefs?.global_enabled ? 'translate-x-5' : 'translate-x-0'
                  )}
                />
              </button>
            </div>
          </div>

          {/* Quiet hours */}
          <div className="bg-bg-surface border border-border-dim rounded-xl p-5">
            <h3 className="text-xs font-display font-bold uppercase tracking-wider text-text-primary mb-4">
              Quiet Hours
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="flex items-center justify-between md:justify-start md:flex-col md:items-start gap-2">
                <label className="text-[11px] text-text-secondary">Enabled</label>
                <button
                  onClick={() => setLocalPrefs((p) => ({ ...(p ?? prefs), quiet_hours_enabled: !(p?.quiet_hours_enabled ?? prefs.quiet_hours_enabled) }))}
                  className={cn(
                    'relative w-11 h-6 rounded-none border transition-colors',
                    localPrefs?.quiet_hours_enabled
                      ? 'bg-accent-cyan border-accent-cyan'
                      : 'bg-bg-elevated border-border-dim'
                  )}
                >
                  <span
                    className={cn(
                      'absolute top-0.5 left-0.5 w-4.5 h-4.5 bg-white rounded-none transition-transform',
                      localPrefs?.quiet_hours_enabled ? 'translate-x-5' : 'translate-x-0'
                    )}
                  />
                </button>
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-[11px] text-text-secondary">Start Time</label>
                <input
                  type="time"
                  value={localPrefs?.quiet_hours_start ?? '22:00'}
                  onChange={(e) => setLocalPrefs((p) => ({ ...(p ?? prefs), quiet_hours_start: e.target.value }))}
                  className="px-2 py-1.5 bg-bg-elevated border border-border-dim text-xs text-text-primary rounded-none focus:border-accent-cyan outline-none"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-[11px] text-text-secondary">End Time</label>
                <input
                  type="time"
                  value={localPrefs?.quiet_hours_end ?? '08:00'}
                  onChange={(e) => setLocalPrefs((p) => ({ ...(p ?? prefs), quiet_hours_end: e.target.value }))}
                  className="px-2 py-1.5 bg-bg-elevated border border-border-dim text-xs text-text-primary rounded-none focus:border-accent-cyan outline-none"
                />
              </div>
            </div>
            <div className="mt-4 flex flex-col gap-1.5">
              <label className="text-[11px] text-text-secondary">Timezone</label>
              <input
                type="text"
                value={localPrefs?.timezone ?? 'UTC'}
                onChange={(e) => setLocalPrefs((p) => ({ ...(p ?? prefs), timezone: e.target.value }))}
                className="px-2 py-1.5 bg-bg-elevated border border-border-dim text-xs text-text-primary rounded-none focus:border-accent-cyan outline-none w-full md:w-64"
                placeholder="UTC"
              />
            </div>
          </div>

          {/* Category list */}
          <div className="bg-bg-surface border border-border-dim rounded-xl p-5">
            <h3 className="text-xs font-display font-bold uppercase tracking-wider text-text-primary mb-4">
              Categories
            </h3>
            <div className="space-y-3">
              {Object.entries(categories).map(([key, val]) => {
                const isExpanded = expanded[key] ?? false
                const disabledGlobally = !localPrefs?.global_enabled
                const categoryDisabled = !val?.enabled || disabledGlobally
                const isWebPushSelected = val?.channels?.includes('web_push') ?? false
                const webPushHint = isWebPushSelected && !isSubscribed && isSupported && !disabledGlobally

                return (
                  <div
                    key={key}
                    className={cn(
                      'border border-border-dim/50 rounded-lg overflow-hidden',
                      categoryDisabled && 'opacity-70'
                    )}
                  >
                    <button
                      onClick={() => setExpanded((e) => ({ ...e, [key]: !isExpanded }))}
                      className="w-full flex items-center justify-between p-3 bg-bg-base/50 hover:bg-bg-base transition-colors text-left"
                    >
                      <div className="flex items-center gap-3">
                        <div className="flex flex-col">
                          <p className="text-xs font-medium text-text-primary capitalize">
                            {key.replace(/_/g, ' ')}
                          </p>
                          <p className="text-[10px] text-text-muted max-w-[200px] truncate">
                            {CATEGORY_DESCRIPTIONS[key] ?? `Priority: ${val?.priority ?? 'normal'}`}
                          </p>
                        </div>
                        <span
                          className={cn(
                            'text-[9px] px-1.5 py-0.5 rounded-none border uppercase font-mono-data',
                            val?.priority === 'critical'
                              ? 'bg-accent-red/10 text-accent-red border-accent-red/30'
                              : val?.priority === 'high'
                              ? 'bg-accent-amber/10 text-accent-amber border-accent-amber/30'
                              : 'bg-bg-elevated text-text-muted border-border-dim'
                          )}
                        >
                          {val?.priority ?? 'normal'}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setCategoryEnabled(key, !val?.enabled)
                          }}
                          disabled={disabledGlobally}
                          className={cn(
                            'relative w-9 h-5 rounded-none border transition-colors',
                            val?.enabled && !disabledGlobally
                              ? 'bg-accent-cyan border-accent-cyan'
                              : 'bg-bg-elevated border-border-dim',
                            disabledGlobally && 'opacity-40 cursor-not-allowed'
                          )}
                        >
                          <span
                            className={cn(
                              'absolute top-0.5 left-0.5 w-3.5 h-3.5 bg-white rounded-none transition-transform',
                              val?.enabled && !disabledGlobally ? 'translate-x-4' : 'translate-x-0'
                            )}
                          />
                        </button>
                        {isExpanded ? (
                          <ChevronUp className="w-4 h-4 text-text-muted" />
                        ) : (
                          <ChevronDown className="w-4 h-4 text-text-muted" />
                        )}
                      </div>
                    </button>

                    <AnimatePresence>
                      {isExpanded && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.15 }}
                          className="overflow-hidden"
                        >
                          <div className="p-3 pt-2 border-t border-border-dim/50">
                            <p className="text-[10px] text-text-muted mb-2 font-mono-data uppercase tracking-wider">
                              Delivery channels
                            </p>
                            <div className="flex flex-wrap gap-2">
                              {(val?.channels ?? []).map((channel) => {
                                const meta = CHANNEL_META[channel]
                                if (!meta) return null
                                const Icon = meta.icon
                                const isChannelDisabled = categoryDisabled || (channel === 'web_push' && !isSubscribed)
                                return (
                                  <button
                                    key={channel}
                                    onClick={() => toggleChannel(key, channel)}
                                    disabled={categoryDisabled || (channel === 'web_push' && !isSubscribed)}
                                    title={meta.label}
                                    className={cn(
                                      'inline-flex items-center gap-1.5 px-2 py-1.5 border text-[10px] font-medium transition-colors',
                                      !isChannelDisabled
                                        ? 'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/30'
                                        : 'bg-bg-elevated text-text-muted border-border-dim'
                                    )}
                                  >
                                    <Icon className="w-3.5 h-3.5" />
                                    {meta.label}
                                  </button>
                                )
                              })}
                            </div>
                            {webPushHint && (
                              <p className="mt-2 text-[10px] text-accent-amber">
                                Enable Web Push above to receive these alerts outside the browser.
                              </p>
                            )}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Save */}
          <div className="flex flex-col items-end gap-2">
            {update.isError && (
              <div className="w-full p-2 bg-accent-red/10 border border-accent-red/30 text-[10px] text-accent-red">
                Save failed: {update.error instanceof Error ? update.error.message : 'Unknown error'}
              </div>
            )}
            {update.isSuccess && !update.isPending && (
              <div className="w-full p-2 bg-accent-green/10 border border-accent-green/30 text-[10px] text-accent-green">
                Preferences saved.
              </div>
            )}
            <button
              onClick={() => {
                if (!localPrefs) return
                // Only send fields the backend expects to avoid accidental
                // validation failures from stale/unknown keys.
                const payload: Partial<NotificationPreferences> = {
                  global_enabled: localPrefs.global_enabled,
                  quiet_hours_enabled: localPrefs.quiet_hours_enabled,
                  quiet_hours_start: localPrefs.quiet_hours_start,
                  quiet_hours_end: localPrefs.quiet_hours_end,
                  timezone: localPrefs.timezone,
                  quiet_hours_exceptions: localPrefs.quiet_hours_exceptions,
                  categories: localPrefs.categories,
                }
                update.mutate(payload)
              }}
              disabled={update.isPending || !localPrefs}
              className={cn(
                'inline-flex items-center gap-2 px-4 py-2 rounded-none',
                'bg-accent-cyan text-white text-xs font-mono-data uppercase tracking-wider',
                'border border-accent-cyan hover:bg-accent-cyan/90 transition-colors',
                'disabled:opacity-50 disabled:cursor-not-allowed'
              )}
            >
              {update.isPending && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              <Save className="w-3.5 h-3.5" />
              Save Preferences
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
