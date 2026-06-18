import { useState, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { BrowserRouter, Routes, Route, useLocation, useNavigate } from 'react-router-dom'
import { BoardSocketProvider } from '@/contexts/BoardSocketContext'
import { Header } from '@/components/Header'
import { Sidebar } from '@/components/Sidebar'
import { KanbanBoard } from '@/components/KanbanBoard'
import { CalendarPage } from '@/components/CalendarPage'
import { DashboardPage } from '@/components/DashboardPage'
import { SessionsPage } from '@/components/SessionsPage'
import { ArchivedSessionsPage } from '@/components/ArchivedSessionsPage'
import { ConversationsPage } from '@/components/ConversationsPage'
import { CouncilPage } from '@/components/CouncilPage'
import { KeeperDashboard } from '@/components/KeeperDashboard'
import { AgentsPage } from '@/components/AgentsPage'
import { AgentDetailPage } from '@/components/AgentDetailPage'
import { AgentChannelsPage } from '@/components/AgentChannelsPage'
import { CreateAgentPage } from '@/components/CreateAgentPage'
import { AgentLogsPage } from '@/components/AgentLogsPage'
import { AgentMemoryPage } from '@/components/AgentMemoryPage'
import { AgentModelPage } from '@/components/AgentModelPage'
import { AgentSecretsPage } from '@/components/AgentSecretsPage'
import { AgentSkillsPage } from '@/components/AgentSkillsPage'
import { AgentJournalsPage } from '@/components/AgentJournalsPage'
import { SkillsStorePage } from '@/components/SkillsStorePage'
import { WorkspacesPage } from '@/components/WorkspacesPage'
import { WorkspaceDetailPage } from '@/components/WorkspaceDetailPage'
import { SharedWorkspacesPage } from '@/components/SharedWorkspacesPage'
import { SharedWorkspaceDetailPage } from '@/components/SharedWorkspaceDetailPage'
import { LogsPage } from '@/components/LogsPage'
import { LoginPage } from '@/components/LoginPage'
import { TaskDetailModal } from '@/components/TaskDetailModal'
import { CostAnalyticsPage } from '@/components/CostAnalyticsPage'
import { SettingsPage } from '@/components/SettingsPage'
import { ProviderSettingsPage } from '@/components/ProviderSettingsPage'
import { LocalModelSettings } from '@/components/LocalModelSettings'
import { GeneralSettingsPage } from '@/components/GeneralSettingsPage'
import { AppearanceSettingsPage } from '@/components/AppearanceSettingsPage'
import { SecuritySettingsPage } from '@/components/SecuritySettingsPage'
import { PromptsPage } from '@/components/PromptsPage'
import { SystemSettingsPage } from '@/components/SystemSettingsPage'
import { NotificationPreferencesPage } from '@/components/NotificationPreferences'
import { DigestPage } from '@/components/DigestPage'
import { ConfirmationModal } from '@/components/ui/ConfirmationModal'
import PWAReloadPrompt from '@/components/PWAReloadPrompt'
import { useAgents } from '@/hooks/useAgents'
import { useTasks } from '@/hooks/useTasks'
import { useCostDashboard } from '@/hooks/useCostDashboard'
import { useBoardSocket } from '@/hooks/useBoardSocket'
import { useAuth } from '@/hooks/useAuth'
import { postJSON, deleteJSON, putJSON } from '@/lib/api'
import type { Agent, Task, Session } from '@/types'

function AppContent() {
  const queryClient = useQueryClient()
  const location = useLocation()
  const navigate = useNavigate()
  const { isAuthenticated, logout } = useAuth()
  const { data: agents = [] } = useAgents()
  const { data: tasks = [] } = useTasks()
  const { data: cost = null } = useCostDashboard()
  const { lastMessage } = useBoardSocket()

  // Sync selected task with URL param
  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const taskId = params.get('task')
    if (taskId && tasks.length > 0) {
      const task = tasks.find((t) => t.id === taskId)
      if (task) {
        setSelectedTask(task)
      }
    }
  }, [location.search, tasks])

  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      return localStorage.getItem('isli-sidebar-collapsed') === 'true'
    } catch {
      return false
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem('isli-sidebar-collapsed', sidebarCollapsed.toString())
    } catch {
      // ignore
    }
  }, [sidebarCollapsed])

  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const [mobileSidebarPage, setMobileSidebarPage] = useState(0)
  const [selectedTask, setSelectedTask] = useState<Task | null>(null)

  const handleCloseTaskModal = () => {
    setSelectedTask(null)
    const params = new URLSearchParams(location.search)
    if (params.has('task')) {
      params.delete('task')
      const search = params.toString()
      navigate(location.pathname + (search ? `?${search}` : ''), { replace: true })
    }
  }

  const [confirmModal, setConfirmModal] = useState<{
    open: boolean;
    title: string;
    description: string;
    onConfirm: () => void | Promise<void>;
  }>({
    open: false,
    title: '',
    description: '',
    onConfirm: () => {},
  })

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
        // Also invalidate chat-sessions and session-history for the new /chats page
        queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
        queryClient.invalidateQueries({ queryKey: ['session-history', session_id] })
        break
      }
      case 'session:stream_event': {
        const { session_id } = lastMessage.payload
        queryClient.setQueryData(['chat-sessions'], (old: Session[] | undefined) =>
          old?.map((s) =>
            s.id === session_id
              ? { ...s, last_activity_at: new Date().toISOString() }
              : s
          ) ?? old
        )
        break
      }
      case 'room:updated':
      case 'room:agent_joined': {
        const roomId = lastMessage.payload?.room_id
        if (roomId) {
          queryClient.invalidateQueries({ queryKey: ['rooms', roomId] })
          queryClient.invalidateQueries({ queryKey: ['room-history', roomId] })
        }
        queryClient.invalidateQueries({ queryKey: ['rooms'] })
        break
      }
      case 'notification:new': {
        queryClient.invalidateQueries({ queryKey: ['notifications'] })
        queryClient.invalidateQueries({ queryKey: ['notifications', 'unread-count'] })
        break
      }
      case 'notification:read': {
        queryClient.invalidateQueries({ queryKey: ['notifications'] })
        queryClient.invalidateQueries({ queryKey: ['notifications', 'unread-count'] })
        break
      }
      case 'notification:read_all': {
        queryClient.invalidateQueries({ queryKey: ['notifications'] })
        queryClient.invalidateQueries({ queryKey: ['notifications', 'unread-count'] })
        break
      }
    }
  }, [lastMessage, queryClient])

  const handleAuthError = (err: unknown) => {
    const msg = err instanceof Error ? err.message : ''
    if (msg.includes('401') || msg.includes('403')) {
      logout()
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

  const updateTaskSchedule = async (id: string, data: { scheduled_at?: string | null, cron_expression?: string | null }) => {
    const previousTasks = queryClient.getQueryData<Task[]>(['tasks'])
    queryClient.setQueryData(['tasks'], (old: Task[] | undefined) =>
      old?.map((t) => (t.id === id ? { ...t, ...data, status: (data.scheduled_at || data.cron_expression) ? 'pending' : t.status } : t)) || []
    )

    try {
      await putJSON(`/v1/tasks/${id}`, { 
        ...data, 
        status: (data.scheduled_at || data.cron_expression) ? 'pending' : undefined 
      })
    } catch (err) {
      queryClient.setQueryData(['tasks'], previousTasks)
      console.error('Failed to update task schedule:', err)
    }
  }

  const deleteTask = async (id: string) => {
    setConfirmModal({
      open: true,
      title: 'Delete Task',
      description: 'Are you sure you want to delete this task? This action cannot be undone.',
      onConfirm: async () => {
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
    })
  }

  // Global Auth Barrier
  if (!isAuthenticated) {
    return <LoginPage />
  }

  return (
    <div className="h-screen bg-bg-base text-text-primary flex flex-col relative overflow-hidden">
      <Header
        mobileNavOpen={mobileSidebarOpen}
        onToggleMobileSidebar={(page) => {
          if (page !== undefined) setMobileSidebarPage(page)
          setMobileSidebarOpen((v) => !v)
        }}
      />
      <div className="flex-1 flex overflow-hidden relative z-10">
        <Sidebar
          agents={agents}
          cost={cost}
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed((v) => !v)}
          mobileOpen={mobileSidebarOpen}
          onCloseMobile={() => setMobileSidebarOpen(false)}
          initialMobilePage={mobileSidebarPage}
        />
        
        <Routes>
          <Route path="/" element={<CouncilPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route
            path="/kanban"
            element={
              <KanbanBoard
                tasks={tasks}
                onMove={moveTask}
                onSchedule={(id, date) => updateTaskSchedule(id, { scheduled_at: date })}
                onDelete={deleteTask}
                onShowDetail={setSelectedTask}
                agents={agents}
                onAuthRequired={logout}
              />
            }
          />

          <Route path="/calendar" element={<CalendarPage />} />

          <Route path="/sessions" element={<SessionsPage />} />
          <Route path="/archive/sessions" element={<ArchivedSessionsPage />} />
          <Route path="/chats" element={<ConversationsPage />} />
          <Route path="/keeper" element={<KeeperDashboard />} />
          <Route path="/logs" element={<LogsPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/agents/new" element={<CreateAgentPage />} />
          <Route path="/store" element={<SkillsStorePage />} />
          <Route path="/agents/:id" element={<AgentDetailPage />} />
          <Route path="/agents/:id/channels" element={<AgentChannelsPage />} />
          <Route path="/agents/:id/logs" element={<AgentLogsPage />} />
          <Route path="/agents/:id/memory" element={<AgentMemoryPage />} />
          <Route path="/agents/:id/model" element={<AgentModelPage />} />
          <Route path="/agents/:id/journals" element={<AgentJournalsPage />} />
          <Route path="/agents/:id/secrets" element={<AgentSecretsPage />} />

          <Route path="/agents/:id/skills" element={<AgentSkillsPage />} />
          <Route path="/workspaces" element={<WorkspacesPage />} />
          <Route path="/workspaces/:id" element={<WorkspaceDetailPage />} />
          <Route path="/shared-workspaces" element={<SharedWorkspacesPage />} />
          <Route path="/shared-workspaces/:id" element={<SharedWorkspaceDetailPage />} />
          <Route path="/costs" element={<CostAnalyticsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/settings/general" element={<GeneralSettingsPage />} />
          <Route path="/settings/appearance" element={<AppearanceSettingsPage />} />
          <Route path="/settings/providers" element={<ProviderSettingsPage />} />
          <Route path="/settings/security" element={<SecuritySettingsPage />} />
          <Route path="/settings/system" element={<SystemSettingsPage />} />
          <Route path="/settings/keeper" element={<LocalModelSettings />} />
          <Route path="/settings/prompts" element={<PromptsPage />} />
          <Route path="/settings/notifications" element={<NotificationPreferencesPage />} />
          <Route path="/digests" element={<DigestPage />} />
        </Routes>
      </div>

      <TaskDetailModal
        open={!!selectedTask}
        task={selectedTask}
        agents={agents}
        tasks={tasks}
        onUpdateSchedule={(data) => selectedTask && updateTaskSchedule(selectedTask.id, data)}
        onClose={handleCloseTaskModal}
      />
      <ConfirmationModal
        open={confirmModal.open}
        title={confirmModal.title}
        description={confirmModal.description}
        variant="danger"
        onConfirm={confirmModal.onConfirm}
        onClose={() => setConfirmModal(prev => ({ ...prev, open: false }))}
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
