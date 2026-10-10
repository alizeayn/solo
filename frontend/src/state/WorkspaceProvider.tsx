/**
 * Workspace state provider.
 *
 * Holds the single active project, its tasks/messages and the live event feed.
 * The backend remains the source of truth: this provider only mirrors it and
 * applies live WebSocket deltas on top.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import { ApiError, api } from '../api/client'
import { useWebSocket } from '../hooks/useWebSocket'
import {
  isActive,
  type AppEvent,
  type AppSettings,
  type CheckResult,
  type ConnectionState,
  type Message,
  type MessageDispatchResult,
  type OrchestrationView,
  type Project,
  type Task,
  type WsEnvelope,
} from '../types'

const PROJECT_STORAGE_KEY = 'solo.projectId'

interface WorkspaceContextValue {
  projects: Project[]
  project: Project | null
  selectProject: (projectId: string | null) => void
  tasks: Task[]
  selectedTaskId: string | null
  selectedTask: Task | null
  selectTask: (taskId: string | null) => void
  activeTask: Task | null
  runningCount: number
  events: AppEvent[]
  messages: Message[]
  settings: AppSettings | null
  /** Live orchestrator working memory for the selected project. */
  orchestration: OrchestrationView['summary'] | null
  /** Most recent Pyright run, pushed as a `check.result` event. */
  lastCheck: CheckResult | null
  connection: ConnectionState
  busy: boolean
  error: string | null
  dismissError: () => void
  reportError: (message: string) => void
  refreshProjects: () => Promise<void>
  refreshSettings: () => Promise<void>
  startCodingTask: (instruction: string) => Promise<void>
  sendMessage: (content: string) => Promise<MessageDispatchResult>
  cancelTask: (taskId: string) => Promise<void>
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null)

export function useWorkspace(): WorkspaceContextValue {
  const value = useContext(WorkspaceContext)
  if (value === null) {
    throw new Error('useWorkspace must be used inside <WorkspaceProvider>')
  }
  return value
}

function upsertTask(tasks: Task[], incoming: Task): Task[] {
  const index = tasks.findIndex((task) => task.id === incoming.id)
  if (index === -1) return [incoming, ...tasks]
  const next = [...tasks]
  next[index] = { ...next[index], ...incoming }
  return next
}

function appendUnique<T extends { id: string | number }>(items: T[], incoming: T): T[] {
  if (items.some((item) => item.id === incoming.id)) return items
  return [...items, incoming]
}

export function WorkspaceProvider({
  children,
  onSignedOut,
}: {
  children: ReactNode
  onSignedOut: () => void
}) {
  const [projects, setProjects] = useState<Project[]>([])
  const [projectId, setProjectId] = useState<string | null>(() =>
    typeof window === 'undefined' ? null : window.localStorage.getItem(PROJECT_STORAGE_KEY),
  )
  const [tasks, setTasks] = useState<Task[]>([])
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [events, setEvents] = useState<AppEvent[]>([])
  const [messages, setMessages] = useState<Message[]>([])
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [orchestration, setOrchestration] = useState<OrchestrationView['summary'] | null>(null)
  const [lastCheck, setLastCheck] = useState<CheckResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Refs let the WebSocket handler read the latest selection without forcing
  // the socket to reconnect whenever the selection changes.
  const selectedTaskIdRef = useRef<string | null>(null)
  selectedTaskIdRef.current = selectedTaskId
  const projectIdRef = useRef<string | null>(null)
  projectIdRef.current = projectId

  const reportError = useCallback((message: string) => setError(message), [])
  const dismissError = useCallback(() => setError(null), [])

  const handleFailure = useCallback(
    (cause: unknown) => {
      if (cause instanceof ApiError && cause.status === 401) {
        onSignedOut()
        return
      }
      const message = cause instanceof Error ? cause.message : String(cause)
      setError(message)
    },
    [onSignedOut],
  )

  const project = useMemo(
    () => projects.find((item) => item.id === projectId) ?? null,
    [projects, projectId],
  )

  const selectedTask = useMemo(
    () => tasks.find((task) => task.id === selectedTaskId) ?? null,
    [tasks, selectedTaskId],
  )

  const activeTask = useMemo(() => tasks.find(isActive) ?? null, [tasks])
  const runningCount = useMemo(() => tasks.filter(isActive).length, [tasks])

  const refreshProjects = useCallback(async () => {
    try {
      const list = await api.projects.list()
      setProjects(list)
      setProjectId((current) => {
        if (current && list.some((item) => item.id === current)) return current
        return list[0]?.id ?? null
      })
    } catch (cause) {
      handleFailure(cause)
    }
  }, [handleFailure])

  const refreshSettings = useCallback(async () => {
    try {
      setSettings(await api.settings.get())
    } catch (cause) {
      handleFailure(cause)
    }
  }, [handleFailure])

  // Initial load.
  useEffect(() => {
    void refreshProjects()
    void refreshSettings()
  }, [refreshProjects, refreshSettings])

  // Persist the selected project.
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (projectId) window.localStorage.setItem(PROJECT_STORAGE_KEY, projectId)
    else window.localStorage.removeItem(PROJECT_STORAGE_KEY)
  }, [projectId])

  // Load tasks + messages whenever the active project changes.
  useEffect(() => {
    if (!projectId) {
      setTasks([])
      setMessages([])
      setSelectedTaskId(null)
      setEvents([])
      return
    }
    let cancelled = false
    const load = async () => {
      try {
        const [taskList, messageList] = await Promise.all([
          api.tasks.list(projectId),
          api.messages.list(projectId),
        ])
        if (cancelled) return
        setTasks(taskList)
        setMessages(messageList)
        setSelectedTaskId((current) => {
          if (current && taskList.some((task) => task.id === current)) return current
          return taskList[0]?.id ?? null
        })
      } catch (cause) {
        if (!cancelled) handleFailure(cause)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [projectId, handleFailure])

  // Load the event history for the selected task.
  useEffect(() => {
    if (!selectedTaskId) {
      setEvents([])
      return
    }
    let cancelled = false
    const load = async () => {
      try {
        const list = await api.tasks.events(selectedTaskId)
        if (!cancelled) setEvents(list)
      } catch (cause) {
        if (!cancelled) handleFailure(cause)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [selectedTaskId, handleFailure])

  const handleEnvelope = useCallback((envelope: WsEnvelope) => {
    if (envelope.channel === 'task') {
      const task = envelope.payload as unknown as Task
      if (task.project_id === projectIdRef.current) {
        setTasks((previous) => upsertTask(previous, task))
      }
      return
    }
    if (envelope.channel === 'event') {
      const event = envelope.payload as unknown as AppEvent
      if (event.type === 'check.result') {
        setLastCheck(event.data as unknown as CheckResult)
      }
      if (event.task_id === selectedTaskIdRef.current) {
        setEvents((previous) => appendUnique(previous, event))
      }
      return
    }
    if (envelope.channel === 'message') {
      const message = envelope.payload as unknown as Message
      setMessages((previous) => appendUnique(previous, message))
      return
    }
    if (envelope.channel === 'orchestration') {
      setOrchestration(envelope.payload as unknown as OrchestrationView['summary'])
    }
  }, [])

  const connection = useWebSocket(handleEnvelope, true)

  const selectProject = useCallback((nextId: string | null) => {
    setProjectId(nextId)
    setSelectedTaskId(null)
    setEvents([])
  }, [])

  const selectTask = useCallback((taskId: string | null) => setSelectedTaskId(taskId), [])

  const startCodingTask = useCallback(
    async (instruction: string) => {
      if (!projectIdRef.current) return
      setBusy(true)
      try {
        const task = await api.tasks.create(projectIdRef.current, instruction)
        setTasks((previous) => upsertTask(previous, task))
        setSelectedTaskId(task.id)
      } catch (cause) {
        handleFailure(cause)
        throw cause
      } finally {
        setBusy(false)
      }
    },
    [handleFailure],
  )

  const sendMessage = useCallback(
    async (content: string) => {
      const currentProject = projectIdRef.current
      if (!currentProject) throw new Error('Select a project first.')
      setBusy(true)
      try {
        const result = await api.messages.send(currentProject, content)
        // Re-fetch so the user's own message (which is not broadcast) appears.
        setMessages(await api.messages.list(currentProject))
        if (result.task_id) setSelectedTaskId(result.task_id)
        if (result.task_id) {
          const task = await api.tasks.get(result.task_id)
          setTasks((previous) => upsertTask(previous, task))
        }
        return result
      } catch (cause) {
        handleFailure(cause)
        throw cause
      } finally {
        setBusy(false)
      }
    },
    [handleFailure],
  )

  const cancelTask = useCallback(
    async (taskId: string) => {
      try {
        const task = await api.tasks.cancel(taskId)
        setTasks((previous) => upsertTask(previous, task))
      } catch (cause) {
        handleFailure(cause)
      }
    },
    [handleFailure],
  )

  const value: WorkspaceContextValue = {
    projects,
    project,
    selectProject,
    tasks,
    selectedTaskId,
    selectedTask,
    selectTask,
    activeTask,
    runningCount,
    events,
    messages,
    settings,
    orchestration,
    lastCheck,
    connection,
    busy,
    error,
    dismissError,
    reportError,
    refreshProjects,
    refreshSettings,
    startCodingTask,
    sendMessage,
    cancelTask,
  }

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
}
