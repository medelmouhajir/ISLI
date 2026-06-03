import { useState, useCallback } from 'react'
import type { UiComponentProps } from './UiComponentRegistry'
import { cn } from '@/lib/utils'
import { ChevronDown, ChevronRight } from 'lucide-react'

interface JsonNodeProps {
  data: unknown
  depth?: number
  keyName?: string
  isLast?: boolean
}

function JsonNode({ data, depth = 0, keyName, isLast = true }: JsonNodeProps) {
  const [collapsed, setCollapsed] = useState(false)
  const indent = depth * 12

  const isObject = data !== null && typeof data === 'object'
  const isArray = Array.isArray(data)
  const isExpandable = isObject && data !== null
  const entries = isObject && data !== null ? Object.entries(data) : []
  const length = isArray ? (data as unknown[]).length : entries.length

  const typeColor = useCallback((value: unknown): string => {
    if (value === null) return 'text-accent-red'
    if (typeof value === 'boolean') return 'text-accent-green'
    if (typeof value === 'number') return 'text-accent-amber'
    if (typeof value === 'string') return 'text-accent-cyan'
    return 'text-text-primary'
  }, [])

  const formatValue = useCallback((value: unknown): string => {
    if (value === null) return 'null'
    if (typeof value === 'boolean') return String(value)
    if (typeof value === 'number') return String(value)
    if (typeof value === 'string') return `"${value}"`
    return ''
  }, [])

  if (!isExpandable) {
    return (
      <div className="font-mono text-[11px] leading-relaxed">
        {keyName !== undefined && (
          <span className="text-text-muted mr-1">{keyName}:</span>
        )}
        <span className={typeColor(data)}>{formatValue(data)}</span>
        {!isLast && <span className="text-text-muted">,</span>}
      </div>
    )
  }

  const bracketOpen = isArray ? '[' : '{'
  const bracketClose = isArray ? ']' : '}'

  return (
    <div className="font-mono text-[11px] leading-relaxed">
      <div className="flex items-center">
        <button
          type="button"
          onClick={() => setCollapsed(!collapsed)}
          className="inline-flex items-center text-text-muted hover:text-accent-cyan transition-colors mr-1"
          aria-label={collapsed ? 'Expand' : 'Collapse'}
        >
          {collapsed ? (
            <ChevronRight className="w-3 h-3" />
          ) : (
            <ChevronDown className="w-3 h-3" />
          )}
        </button>
        {keyName !== undefined && (
          <span className="text-text-muted mr-1">{keyName}:</span>
        )}
        <span className="text-text-secondary">
          {bracketOpen}
          {collapsed && (
            <span className="text-text-muted mx-1">
              {length} {isArray ? 'items' : 'keys'}
            </span>
          )}
          {collapsed && bracketClose}
        </span>
        {!isLast && !collapsed && <span className="text-text-muted">,</span>}
      </div>
      {!collapsed && (
        <div
          className="border-l border-border-dim/30 pl-2 ml-1.5"
          style={{ marginLeft: `${indent + 4}px` }}
        >
          {entries.map(([k, v], i) => (
            <JsonNode
              key={isArray ? i : k}
              data={v}
              depth={depth + 1}
              keyName={isArray ? String(i) : k}
              isLast={i === entries.length - 1}
            />
          ))}
          <div>
            <span className="text-text-secondary">{bracketClose}</span>
            {!isLast && <span className="text-text-muted">,</span>}
          </div>
        </div>
      )}
    </div>
  )
}

export function JsonViewer({ payload }: UiComponentProps) {
  const { props } = payload
  const title = (props.title ?? '') as string
  const data = props.data
  const initiallyCollapsed = Boolean(props.collapsed)

  const [collapsed, setCollapsed] = useState(initiallyCollapsed)

  return (
    <div className="border border-border-dim bg-bg-elevated p-4 space-y-2">
      {title && (
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-bold text-accent-cyan uppercase tracking-wider">
            {title}
          </h4>
          <button
            type="button"
            onClick={() => setCollapsed(!collapsed)}
            className="text-[9px] font-mono text-text-muted hover:text-accent-cyan uppercase tracking-widest transition-colors"
          >
            {collapsed ? 'Expand' : 'Collapse'}
          </button>
        </div>
      )}
      <div className={cn('overflow-auto max-h-[400px]', !title && 'pt-1')}>
        {data !== undefined && data !== null ? (
          <JsonNode data={data} depth={0} isLast />
        ) : (
          <span className="text-[11px] font-mono text-text-muted">No data</span>
        )}
      </div>
    </div>
  )
}
