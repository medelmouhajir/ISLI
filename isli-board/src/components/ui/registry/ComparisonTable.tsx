import type { UiComponentProps } from './UiComponentRegistry'

export function ComparisonTable({ payload }: UiComponentProps) {
  const { props } = payload
  const headers = (props.headers ?? []) as string[]
  const rows = (props.rows ?? []) as string[][]

  return (
    <div className="border border-border-dim bg-bg-elevated overflow-x-auto">
      <table className="w-full text-xs font-mono">
        <thead>
          <tr className="border-b border-border-dim text-text-muted uppercase">
            {headers.map((h, i) => (
              <th key={i} className="px-3 py-2 text-left">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} className="border-b border-border-dim/50">
              {row.map((cell, ci) => (
                <td key={ci} className="px-3 py-2 text-text-primary">{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
