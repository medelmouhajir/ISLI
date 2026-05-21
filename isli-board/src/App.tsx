import { useState, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { BoardSocketProvider } from '@/contexts/BoardSocketContext'
import { Header } from '@/components/Header'
import { Sidebar } from '@/components/Sidebar'
import { KanbanBoard } from '@/components/KanbanBoard'
import { SessionsPage } from '@/components/SessionsPage'
import { KeeperDashboard } from '@/components/KeeperDashboard'
import { AgentsPage } from '@/components/AgentsPage'
import { AgentDetailPage } from '@/components/AgentDetailPage'
import { AgentLogsPage } from '@/components/AgentLogsPage'
import { WorkspacesPage } from '@/components/WorkspacesPage'
import { WorkspaceDetailPage } from '@/components/WorkspaceDetailPage'
import { LoginModal } from '@/components/LoginModal'
import { TaskDetailModal } from '@/components/TaskDetailModal'
import PWAReloadPrompt from '@/components/PWAReloadPrompt'
import { useAgents } from '@/hooks/useAgents'
import { useTasks } from '@/hooks/useTasks'
import { useCostDashboard } from '@/hooks/useCostDashboard'
import { useBoardSocket } from '@/hooks/useBoardSocket'
import { postJSON, deleteJSON, putJSON } from '@/lib/api'
import type { Agent, Task, Session } from '@/types'

function AppContent() {
  const queryClient = useQueryClient()
  const { data: agents = [] } = useAgents()
  const { data: tasks = [] } = useTasks()
  const { data: cost = null } = useCostDashboard()
  const { lastMessage } = useBoardSocket()

  const [showLoginModal, setShowLoginModal] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const [selectedTask, setSelectedTask] = useState<Task | null>(null)

  // WebSocket real-time updates
  useEffect(() => {
    if (!lastMessage) return

    switch (lastMessage.type) {
      case 'task:created': {
        const task = lastMessage.payload.task as unknown as Task
        queryClient.setQueryData(['tasks'], (old: Task[] | undefined) =>
          old ? [task, ...old] : [task]
        )
        break
      }
      case 'task:updated':
      case 'task:moved': {
        const { task_id, task: payloadTask } = lastMessage.payload
        queryClient.setQueryData(['tasks'], (old: Task[] | undefined) =>
          old?.map((t) => (t.id === task_id ? ({ ...t, ...payloadTask } as Task) : t)) || []
        )
        break
      }
      case 'agent:heartbeat':
      case 'agent:online': {
        const payload = lastMessage.payload
        queryClient.setQueryData(['agents'], (old: Agent[] | undefined) =>
          old?.map((a) => (a.id === payload.agent_id ? ({ ...a, ...payload } as Agent) : a)) || []
        )
        break
      }
      case 'session:updated':
      case 'session:message': {
        const { session_id } = lastMessage.payload
        // Update the list cache in-place so the sidebar timestamp refreshes
        // without triggering a full list refetch
        queryClient.setQueryData(['sessions', undefined], (old: Session[] | undefined) =>
          old?.map((s) =>
            s.id === session_id
              ? { ...s, last_activity_at: new Date().toISOString() }
              : s
          ) ?? old
        )
        // Only refetch the detail query; staleTime prevents duplicate fetches
        queryClient.invalidateQueries({ queryKey: ['sessions', session_id] })
        break
      }
    }
  }, [lastMessage, queryClient])

  const handleAuthError = (err: unknown) => {
    const msg = err instanceof Error ? err.message : ''
    if (msg.includes('401') || msg.includes('403')) {
      setShowLoginModal(true)
    }
  }

  const moveTask = async (id: string, status: string) => {
    const previousTasks = queryClient.getQueryData<Task[]>(['tasks'])
    queryClient.setQueryData(['tasks'], (old: Task[] | undefined) =>
      old?.map((t) => (t.id === id ? { ...t, status } : t)) || []
    )
    try {
      await postJSON(`/v1/tasks/${id}/move?new_status=${status}`, {})
    } catch (err) {
      queryClient.setQueryData(['tasks'], previousTasks)
      handleAuthError(err)
      console.error('Failed to move task:', err)
    }
  }

  const scheduleTask = async (id: string, date: string) => {
    const previousTasks = queryClient.getQueryData<Task[]>(['tasks'])
    queryClient.setQueryData(['tasks'], (old: Task[] | undefined) =>
      old?.map((t) => (t.id === id ? { ...t, status: 'pending', scheduled_at: date } : t)) || []
    )
    try {
      await putJSON(`/v1/tasks/${id}`, { status: 'pending', scheduled_at: date })
    } catch (err) {
      queryClient.setQueryData(['tasks'], previousTasks)
      handleAuthError(err)
      console.error('Failed to schedule task:', err)
    }
  }

  const deleteTask = async (id: string) => {
    if (!confirm('Delete task?')) return
    const previousTasks = queryClient.getQueryData<Task[]>(['tasks'])
    queryClient.setQueryData(['tasks'], (old: Task[] | undefined) =>
      old?.filter((t) => t.id !== id) || []
    )
    try {
      await deleteJSON(`/v1/tasks/${id}`)
    } catch (err) {
      queryClient.setQueryData(['tasks'], previousTasks)
      handleAuthError(err)
      console.error('Failed to delete task:', err)
    }
  }

  return (
    <div className="h-screen bg-bg-base text-text-primary flex flex-col relative overflow-hidden">
      <Header
        onLogin={() => setShowLoginModal(true)}
        onToggleMobileSidebar={() => setMobileSidebarOpen((v) => !v)}
      />
      <div className="flex-1 flex overflow-hidden relative z-10">
        <Sidebar
          agents={agents}
          cost={cost}
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed((v) => !v)}
          mobileOpen={mobileSidebarOpen}
          onCloseMobile={() => setMobileSidebarOpen(false)}
        />
        
        <Routes>
          <Route
            path="/"
            element={
              <KanbanBoard
                tasks={tasks}
                onMove={moveTask}
                onSchedule={scheduleTask}
                onDelete={deleteTask}
                onShowDetail={setSelectedTask}
                agents={agents}
                onAuthRequired={() => setShowLoginModal(true)}
              />
            }
          />

          <Route path="/sessions" element={<SessionsPage />} />
          <Route path="/keeper" element={<KeeperDashboard />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/agents/:id" element={<AgentDetailPage />} />
          <Route path="/agents/:id/logs" element={<AgentLogsPage />} />
          <Route path="/workspaces" element={<WorkspacesPage />} />
          <Route path="/workspaces/:id" element={<WorkspaceDetailPage />} />
        </Routes>
      </div>

      <LoginModal
        open={showLoginModal}
        onClose={() => setShowLoginModal(false)}
      />
      <TaskDetailModal
        open={!!selectedTask}
        task={selectedTask}
        agents={agents}
        onClose={() => setSelectedTask(null)}
      />
      <PWAReloadPrompt />
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <BoardSocketProvider>
        <AppContent />
      </BoardSocketProvider>
    </BrowserRouter>
  )
}
