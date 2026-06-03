import type { UiComponentProps } from './UiComponentRegistry'

export function DataTable({ payload, onAction }: UiComponentProps) {
  const { props, action_id } = payload
  const columns = (props.columns ?? []) as Array<{ key: string; label: string }>
  const rows = (props.rows ?? []) as Array<Record<string, unknown>>

  return (
    <div className="border border-border-dim bg-bg-elevated overflow-x-auto">
      <table className="w-full text-xs font-mono">
        <thead>
          <tr className="border-b border-border-dim text-text-muted uppercase">
            {columns.map((c) => (
              <th key={c.key} className="px-3 py-2 text-left">{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr
              key={idx}
              className="border-b border-border-dim/50 hover:bg-accent-cyan/5 cursor-pointer transition-colors"
              onClick={() => {
                if (action_id) {
                  onAction(action_id, 'row_selected', { row_index: idx, row })
                }
              }}
            >
              {columns.map((c) => (
                <td key={c.key} className="px-3 py-2 text-text-primary">{String(row[c.key] ?? '')}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
