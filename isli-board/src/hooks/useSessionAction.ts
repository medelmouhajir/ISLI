import { useMutation } from '@tanstack/react-query'

async function postSessionAction(
  sessionId: string,
  action: { action_id: string; action_type: string; payload: Record<string, unknown> }
) {
  const res = await fetch(`/api/v1/sessions/${sessionId}/action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(action),
  })
  if (!res.ok) throw new Error('Action failed')
  return res.json()
}

export function useSessionAction() {
  return useMutation({
    mutationFn: ({
      sessionId,
      action,
    }: {
      sessionId: string
      action: { action_id: string; action_type: string; payload: Record<string, unknown> }
    }) => postSessionAction(sessionId, action),
  })
}
