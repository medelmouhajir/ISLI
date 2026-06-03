import { useState, useCallback } from 'react'
import type { UiComponentProps } from './UiComponentRegistry'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Select } from '@/components/ui/Select'
import { Toggle } from '@/components/ui/Toggle'
import { Label } from '@/components/ui/Label'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'

interface FormField {
  name: string
  label: string
  type: string
  required?: boolean
  options?: string[]
  default?: string | number | boolean
}

export function FormComponent({ payload, onAction }: UiComponentProps) {
  const { props, action_id } = payload
  const title = (props.title ?? '') as string
  const description = (props.description ?? '') as string
  const fields = (props.fields ?? []) as FormField[]
  const submitLabel = (props.submit_label ?? 'Submit') as string

  const initialValues: Record<string, unknown> = {}
  fields.forEach((field) => {
    if (field.default !== undefined) {
      initialValues[field.name] = field.default
    } else if (field.type === 'toggle') {
      initialValues[field.name] = false
    } else {
      initialValues[field.name] = ''
    }
  })

  const [values, setValues] = useState<Record<string, unknown>>(initialValues)
  const [submitted, setSubmitted] = useState(false)

  const handleChange = useCallback(
    (name: string, value: unknown) => {
      setValues((prev) => ({ ...prev, [name]: value }))
    },
    []
  )

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()
      if (!action_id) return
      setSubmitted(true)
      onAction(action_id, 'form_submitted', { values })
    },
    [action_id, values, onAction]
  )

  return (
    <div className="border border-border-dim bg-bg-elevated p-4 space-y-4">
      {title && (
        <h4 className="text-sm font-bold text-accent-cyan uppercase tracking-wider">
          {title}
        </h4>
      )}
      {description && (
        <p className="text-[11px] font-mono text-text-secondary leading-relaxed">
          {description}
        </p>
      )}
      {submitted ? (
        <div className="text-[10px] font-mono text-accent-green uppercase tracking-widest py-2 border-t border-border-dim/50">
          ✓ Form submitted
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-3">
          {fields.map((field) => (
            <div key={field.name} className="space-y-1">
              <Label className={cn(field.required && 'after:content-["*"] after:text-accent-red after:ml-1')}>
                {field.label}
              </Label>
              {field.type === 'textarea' ? (
                <Textarea
                  value={String(values[field.name] ?? '')}
                  onChange={(e) => handleChange(field.name, e.target.value)}
                  required={field.required}
                />
              ) : field.type === 'select' ? (
                <Select
                  value={String(values[field.name] ?? '')}
                  onChange={(e) => handleChange(field.name, e.target.value)}
                  required={field.required}
                >
                  <option value="">-- SELECT --</option>
                  {(field.options ?? []).map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </Select>
              ) : field.type === 'toggle' ? (
                <Toggle
                  checked={Boolean(values[field.name])}
                  onChange={(checked) => handleChange(field.name, checked)}
                  label={field.label}
                />
              ) : field.type === 'number' ? (
                <Input
                  type="number"
                  value={String(values[field.name] ?? '')}
                  onChange={(e) => handleChange(field.name, e.target.value === '' ? '' : Number(e.target.value))}
                  required={field.required}
                />
              ) : (
                <Input
                  type="text"
                  value={String(values[field.name] ?? '')}
                  onChange={(e) => handleChange(field.name, e.target.value)}
                  required={field.required}
                />
              )}
            </div>
          ))}
          <div className="pt-1">
            <Button type="submit" variant="primary" size="sm" className="w-full">
              {submitLabel}
            </Button>
          </div>
        </form>
      )}
    </div>
  )
}
