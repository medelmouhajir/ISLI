import { useEffect, useState, useCallback } from 'react'

const API_BASE = '/api'

interface Agent {
  id: string
  name: string
  status: string
  model_provider: string | null
  token_budget: number | null
  token_used: number
  heartbeat_at: string | null
}

interface Task {
  id: string
  title: string
  description: string | null
  status: string
  priority: number
  agent_id: string | null
  created_by: string
  created_at: string
  input: string
  output: string | null
  channel: string | null
  depth: number
  tags: string[]
}

interface CostDashboard {
  total_agents: number
  total_tasks: number
  total_cost_usd: number
  avg_cost_per_agent: number
  agent_costs: { agent_id: string; cost_usd: number; tokens: number }[]
}

const COLUMNS = ['inbox', 'doing', 'review', 'done', 'failed']

function usePoll<T>(fetcher: () => Promise<T>, interval = 2000) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const res = await fetcher()
      setData(res)
      setError(null)
    } catch (e) {
      setError(String(e))
    }
  }, [fetcher])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, interval)
    return () => clearInterval(id)
  }, [refresh, interval])

  return { data, error, refresh }
}

async function getJSON(path: string) {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

async function postJSON(path: string, body: unknown) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

async function deleteJSON(path: string) {
  const res = await fetch(`${API_BASE}${path}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    online: 'bg-green-600',
    offline: 'bg-gray-500',
    paused: 'bg-yellow-500',
    registered: 'bg-blue-500',
    deleted: 'bg-red-500',
  }
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold text-white ${colors[status] || 'bg-gray-400'}`}>
      {status}
    </span>
  )
}

function TaskCard({ task, onMove, agents }: { task: Task; onMove: (id: string, status: string) => void; agents: Agent[] }) {
  const agent = agents.find((a) => a.id === task.agent_id)
  const nextMap: Record<string, string> = {
    inbox: 'doing',
    doing: 'review',
    review: 'done',
  }
  return (
    <div className="bg-gray-800 rounded-lg p-3 shadow border border-gray-700 hover:border-gray-600 transition">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold text-gray-100 leading-tight">{task.title}</h3>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-700 text-gray-300">P{task.priority}</span>
      </div>
      {task.description && <p className="text-xs text-gray-400 mt-1 line-clamp-2">{task.description}</p>}
      <div className="mt-2 flex flex-wrap gap-1">
        {task.tags.map((t) => (
          <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-gray-700 text-gray-300">{t}</span>
        ))}
      </div>
      <div className="mt-2 flex items-center justify-between text-[11px] text-gray-400">
        <span>{agent ? agent.name : task.created_by}</span>
        <span>{task.channel || 'core'}</span>
      </div>
      <div className="mt-2 flex items-center gap-1">
        {nextMap[task.status] && (
          <button
            onClick={() => onMove(task.id, nextMap[task.status])}
            className="px-2 py-1 rounded bg-blue-600 hover:bg-blue-500 text-white text-xs"
          >
            → {nextMap[task.status]}
          </button>
        )}
        <button
          onClick={() => onMove(task.id, 'failed')}
          className="px-2 py-1 rounded bg-red-700 hover:bg-red-600 text-white text-xs"
        >
          fail
        </button>
        {task.status === 'failed' && (
          <button
            onClick={() => onMove(task.id, 'inbox')}
            className="px-2 py-1 rounded bg-gray-600 hover:bg-gray-500 text-white text-xs"
          >
            retry
          </button>
        )}
      </div>
    </div>
  )
}

export default function App() {
  const { data: agents, refresh: refreshAgents } = usePoll<Agent[]>(() => getJSON('/v1/agents'), 3000)
  const { data: tasks, refresh: refreshTasks } = usePoll<Task[]>(() => getJSON('/v1/tasks'), 2000)
  const { data: cost } = usePoll<CostDashboard>(() => getJSON('/v1/system/cost/dashboard'), 5000)

  const [showTaskModal, setShowTaskModal] = useState(false)
  const [showAgentModal, setShowAgentModal] = useState(false)

  const moveTask = async (id: string, newStatus: string) => {
    await postJSON(`/v1/tasks/${id}/move?new_status=${newStatus}`, {})
    refreshTasks()
  }

  const createTask = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    await postJSON('/v1/tasks', {
      title: fd.get('title'),
      description: fd.get('description'),
      created_by: fd.get('created_by') || 'board',
      agent_id: fd.get('agent_id') || null,
      priority: Number(fd.get('priority') || 3),
      type: 'task',
    })
    setShowTaskModal(false)
    refreshTasks()
  }

  const createAgent = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    await postJSON('/v1/agents', {
      id: fd.get('id') || undefined,
      name: fd.get('name'),
      description: fd.get('description'),
      model_provider: fd.get('model_provider'),
      model_id: fd.get('model_id'),
      token_budget: fd.get('token_budget') ? Number(fd.get('token_budget')) : null,
    })
    setShowAgentModal(false)
    refreshAgents()
  }

  const deleteTask = async (id: string) => {
    if (!confirm('Delete task?')) return
    await deleteJSON(`/v1/tasks/${id}`)
    refreshTasks()
  }

  const agentsList = agents || []
  const tasksList = tasks || []

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col">
      <header className="border-b border-gray-800 bg-gray-900 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold tracking-tight">ISLI Board</h1>
          <span className="text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-400 border border-gray-700">v1</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowAgentModal(true)}
            className="px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-sm border border-gray-700"
          >
            + Agent
          </button>
          <button
            onClick={() => setShowTaskModal(true)}
            className="px-3 py-1.5 rounded bg-blue-600 hover:bg-blue-500 text-sm font-semibold"
          >
            + Task
          </button>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        <aside className="w-64 border-r border-gray-800 bg-gray-900 flex flex-col overflow-y-auto">
          <div className="p-4 border-b border-gray-800">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3">Agents</h2>
            <div className="space-y-3">
              {agentsList.map((a) => (
                <div key={a.id} className="bg-gray-800 rounded p-2 border border-gray-700">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">{a.name}</span>
                    <StatusBadge status={a.status} />
                  </div>
                  <div className="text-[11px] text-gray-400 mt-1">{a.model_provider || 'no model'}</div>
                  <div className="text-[11px] text-gray-500 mt-1">
                    tokens {a.token_used.toLocaleString()}
                    {a.token_budget ? ` / ${a.token_budget.toLocaleString()}` : ''}
                  </div>
                </div>
              ))}
              {agentsList.length === 0 && (
                <div className="text-xs text-gray-500">No agents registered.</div>
              )}
            </div>
          </div>

          <div className="p-4">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3">Cost</h2>
            {cost ? (
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Agents</span>
                  <span>{cost.total_agents}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Tasks</span>
                  <span>{cost.total_tasks}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Spend</span>
                  <span className="font-semibold">${cost.total_cost_usd.toFixed(4)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Avg/agent</span>
                  <span>${cost.avg_cost_per_agent.toFixed(4)}</span>
                </div>
                {cost.agent_costs.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-gray-800 space-y-1">
                    {cost.agent_costs.map((c) => (
                      <div key={c.agent_id} className="flex justify-between text-[11px]">
                        <span className="text-gray-400 truncate max-w-[100px]">{c.agent_id}</span>
                        <span>${c.cost_usd.toFixed(4)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="text-xs text-gray-500">Loading cost data...</div>
            )}
          </div>
        </aside>

        <main className="flex-1 overflow-x-auto overflow-y-hidden p-4">
          <div className="flex gap-4 h-full min-w-max">
            {COLUMNS.map((col) => {
              const colTasks = tasksList.filter((t) => t.status === col)
              return (
                <div key={col} className="w-80 flex flex-col h-full">
                  <div className="flex items-center justify-between mb-2 px-1">
                    <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-400">{col}</h2>
                    <span className="text-xs px-1.5 py-0.5 rounded bg-gray-800 text-gray-400 border border-gray-700">
                      {colTasks.length}
                    </span>
                  </div>
                  <div className="flex-1 overflow-y-auto space-y-3 pr-1">
                    {colTasks.map((t) => (
                      <div key={t.id} className="relative group">
                        <TaskCard task={t} onMove={moveTask} agents={agentsList} />
                        <button
                          onClick={() => deleteTask(t.id)}
                          className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 text-[10px] px-1.5 py-0.5 rounded bg-red-700 hover:bg-red-600 text-white transition"
                        >
                          delete
                        </button>
                      </div>
                    ))}
                    {colTasks.length === 0 && (
                      <div className="text-xs text-gray-600 text-center py-6 border-2 border-dashed border-gray-800 rounded">
                        No tasks
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </main>
      </div>

      {showTaskModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md shadow-xl">
            <h2 className="text-lg font-semibold mb-4">Create Task</h2>
            <form onSubmit={createTask} className="space-y-3">
              <input name="title" placeholder="Title" required className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
              <textarea name="description" placeholder="Description" rows={3} className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
              <select name="agent_id" className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm">
                <option value="">No agent</option>
                {agentsList.map((a) => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>
              <input name="created_by" placeholder="Created by (default: board)" className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
              <input name="priority" type="number" min={1} max={5} defaultValue={3} className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={() => setShowTaskModal(false)} className="px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-sm">Cancel</button>
                <button type="submit" className="px-3 py-1.5 rounded bg-blue-600 hover:bg-blue-500 text-sm font-semibold">Create</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showAgentModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md shadow-xl">
            <h2 className="text-lg font-semibold mb-4">Create Agent</h2>
            <form onSubmit={createAgent} className="space-y-3">
              <input name="id" placeholder="Agent ID (optional)" className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
              <input name="name" placeholder="Name" required className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
              <input name="description" placeholder="Description" className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
              <input name="model_provider" placeholder="Provider (e.g., anthropic)" className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
              <input name="model_id" placeholder="Model ID (e.g., claude-sonnet-4-6)" className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
              <input name="token_budget" type="number" placeholder="Token budget" className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={() => setShowAgentModal(false)} className="px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-sm">Cancel</button>
                <button type="submit" className="px-3 py-1.5 rounded bg-blue-600 hover:bg-blue-500 text-sm font-semibold">Create</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
