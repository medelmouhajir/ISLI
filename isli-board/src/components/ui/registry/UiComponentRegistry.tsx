import type { ComponentPayload } from '@/types'
import { DataTable } from './DataTable'
import { DetailCard } from './DetailCard'
import { ButtonGroup } from './ButtonGroup'
import { ComparisonTable } from './ComparisonTable'
import { FormComponent } from './FormComponent'
import { JsonViewer } from './JsonViewer'
import { StatusTimeline } from './StatusTimeline'
import { MetricGrid } from './MetricGrid'
import { FileCard } from './FileCard'

export type ComponentType =
  | 'table'
  | 'card'
  | 'button_group'
  | 'comparison_table'
  | 'form'
  | 'json_viewer'
  | 'status_timeline'
  | 'metric_grid'
  | 'file_card'

export interface UiComponentProps {
  payload: ComponentPayload
  sessionId: string
  onAction: (actionId: string, actionType: string, payload: Record<string, unknown>) => void
}

const registry: Record<ComponentType, React.FC<UiComponentProps>> = {
  table: DataTable,
  card: DetailCard,
  button_group: ButtonGroup,
  comparison_table: ComparisonTable,
  form: FormComponent,
  json_viewer: JsonViewer,
  status_timeline: StatusTimeline,
  metric_grid: MetricGrid,
  file_card: FileCard,
}

export function UiComponentRenderer({ payload, sessionId, onAction }: UiComponentProps) {
  const Component = registry[payload.component_type as ComponentType]
  if (!Component) {
    return (
      <pre className="text-xs text-text-muted border border-accent-red/20 bg-accent-red/5 p-2">
        {JSON.stringify(payload, null, 2)}
      </pre>
    )
  }
  return <Component payload={payload} sessionId={sessionId} onAction={onAction} />
}
