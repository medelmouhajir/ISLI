import type { UiComponentProps } from './UiComponentRegistry'

export function DetailCard({ payload, onAction }: UiComponentProps) {
  const { props, action_id } = payload
  const title = (props.title ?? '') as string
  const fields = (props.fields ?? []) as Array<{ label: string; value: string }>
  const buttons = (props.buttons ?? []) as Array<{
    label: string
    action_type: string
    payload?: Record<string, unknown>
  }>

  return (
    <div className="border border-border-dim bg-bg-elevated p-4 space-y-3">
      <h4 className="text-sm font-bold text-accent-cyan uppercase tracking-wider">{title}</h4>
      <div className="space-y-1">
        {fields.map((f, i) => (
          <div key={i} className="flex justify-between text-xs">
            <span className="text-text-muted">{f.label}</span>
            <span className="text-text-primary">{f.value}</span>
          </div>
        ))}
      </div>
      {buttons && buttons.length > 0 && (
        <div className="flex gap-2 pt-2">
          {buttons.map((btn, i) => (
            <button
              key={i}
              className="px-3 py-1.5 text-[10px] font-mono font-bold border border-accent-cyan text-accent-cyan hover:bg-accent-cyan hover:text-bg-base transition-colors"
              onClick={() => {
                if (action_id) {
                  onAction(action_id, btn.action_type, btn.payload ?? {})
                }
              }}
            >
              {btn.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
