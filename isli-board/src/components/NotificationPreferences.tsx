import { useState } from 'react'
import { Bell, Save, Loader2, Info, Share } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useNotificationPreferences, useUpdateNotificationPreferences } from '@/hooks/useNotificationPreferences'
import { useWebPush } from '@/hooks/useWebPush'

export function NotificationPreferencesPage() {
  // TODO: replace with actual logged-in user ID once auth system matures
  const userId = 'admin'
  const { data: prefs, isLoading } = useNotificationPreferences(userId)
  const update = useUpdateNotificationPreferences(userId)
  const { isSupported, isSubscribed, isIOS, isStandalone, subscribe, unsubscribe } = useWebPush(userId)

  const [localPrefs, setLocalPrefs] = useState(prefs)

  if (isLoading || !prefs) {
    return (
      <div className="flex-1 overflow-y-auto bg-bg-base h-full w-full min-h-0 flex items-center justify-center">
        <Loader2 className="w-6 h-6 text-accent-cyan animate-spin" />
      </div>
    )
  }

  const categories = localPrefs?.categories ?? prefs.categories ?? {}

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
                onClick={() => setLocalPrefs((p: any) => ({ ...p, global_enabled: !p?.global_enabled }))}
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
                  onClick={() => setLocalPrefs((p: any) => ({ ...p, quiet_hours_enabled: !p?.quiet_hours_enabled }))}
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
                  onChange={(e) => setLocalPrefs((p: any) => ({ ...p, quiet_hours_start: e.target.value }))}
                  className="px-2 py-1.5 bg-bg-elevated border border-border-dim text-xs text-text-primary rounded-none focus:border-accent-cyan outline-none"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-[11px] text-text-secondary">End Time</label>
                <input
                  type="time"
                  value={localPrefs?.quiet_hours_end ?? '08:00'}
                  onChange={(e) => setLocalPrefs((p: any) => ({ ...p, quiet_hours_end: e.target.value }))}
                  className="px-2 py-1.5 bg-bg-elevated border border-border-dim text-xs text-text-primary rounded-none focus:border-accent-cyan outline-none"
                />
              </div>
            </div>
            <div className="mt-4 flex flex-col gap-1.5">
              <label className="text-[11px] text-text-secondary">Timezone</label>
              <input
                type="text"
                value={localPrefs?.timezone ?? 'UTC'}
                onChange={(e) => setLocalPrefs((p: any) => ({ ...p, timezone: e.target.value }))}
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
              {Object.entries(categories).map(([key, val]: [string, any]) => (
                <div key={key} className="flex items-center justify-between py-2 border-b border-border-dim/50 last:border-0">
                  <div>
                    <p className="text-xs font-medium text-text-primary capitalize">
                      {key.replace(/_/g, ' ')}
                    </p>
                    <p className="text-[10px] text-text-muted">
                      Priority: {val?.priority ?? 'normal'}
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      const next = { ...categories, [key]: { ...val, enabled: !val?.enabled } }
                      setLocalPrefs((p: any) => ({ ...p, categories: next }))
                    }}
                    className={cn(
                      'relative w-11 h-6 rounded-none border transition-colors',
                      val?.enabled
                        ? 'bg-accent-cyan border-accent-cyan'
                        : 'bg-bg-elevated border-border-dim'
                    )}
                  >
                    <span
                      className={cn(
                        'absolute top-0.5 left-0.5 w-4.5 h-4.5 bg-white rounded-none transition-transform',
                        val?.enabled ? 'translate-x-5' : 'translate-x-0'
                      )}
                    />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Save */}
          <div className="flex justify-end">
            <button
              onClick={() => update.mutate(localPrefs ?? {})}
              disabled={update.isPending}
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
