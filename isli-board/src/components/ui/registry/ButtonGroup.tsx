import type { UiComponentProps } from './UiComponentRegistry'

export function ButtonGroup({ payload, onAction }: UiComponentProps) {
  const { props, action_id } = payload
  const buttons = (props.buttons ?? []) as Array<{
    label: string
    action_type: string
    payload?: Record<string, unknown>
  }>

  return (
    <div className="flex flex-wrap gap-2">
      {buttons.map((btn, i) => (
        <button
          key={i}
          className="px-4 py-2 text-xs font-mono font-bold border border-accent-purple text-accent-purple hover:bg-accent-purple hover:text-bg-base transition-colors"
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
  )
}
