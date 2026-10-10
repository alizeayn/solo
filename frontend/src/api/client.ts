/**
 * Typed API client.
 *
 * All requests are same-origin and carry the session cookie
 * (`credentials: 'same-origin'`). Secrets are only ever sent *to* the backend;
 * the backend never returns them.
 */

import type {
  AppEvent,
  FileContent,
  FileLimits,
  PiInstallResult,
  PiRuntime,
  AppSettings,
  AuthStatus,
  CheckResult,
  ChecksStatus,
  ConnectionTestResult,
  FsListing,
  Health,
  MemoryCreate,
  MemoryEntry,
  Message,
  MessageDispatchResult,
  OpenRouterModel,
  OrchestrationView,
  OrchestratorStatus,
  PiAuthStatus,
  PiModel,
  PiProvider,
  PiStatus,
  Project,
  ProjectConfig,
  ProjectSummary,
  ProjectTree,
  SettingsPatch,
  Task,
  TaskDetail,
} from '../types'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(path, {
    credentials: 'same-origin',
    ...init,
    headers,
  })

  if (!response.ok) {
    throw new ApiError(response.status, await extractError(response))
  }

  if (response.status === 204) {
    return undefined as T
  }
  const text = await response.text()
  return (text ? JSON.parse(text) : undefined) as T
}

async function extractError(response: Response): Promise<string> {
  try {
    const data: unknown = await response.json()
    if (data && typeof data === 'object' && 'detail' in data) {
      const detail = (data as { detail: unknown }).detail
      if (typeof detail === 'string') return detail
      if (Array.isArray(detail)) {
        return detail
          .map((item) => (item as { msg?: string }).msg ?? JSON.stringify(item))
          .join('; ')
      }
    }
  } catch {
    /* fall through to the status text */
  }
  return `${response.status} ${response.statusText}`.trim()
}

function json(body: unknown): RequestInit {
  return { method: 'POST', body: JSON.stringify(body) }
}

export const api = {
  auth: {
    status: () => request<AuthStatus>('/api/auth/status'),
    setup: (username: string, password: string) =>
      request<AuthStatus>('/api/auth/setup', json({ username, password })),
    login: (username: string, password: string) =>
      request<AuthStatus>('/api/auth/login', json({ username, password })),
    logout: () => request<AuthStatus>('/api/auth/logout', { method: 'POST' }),
    me: () => request<AuthStatus>('/api/auth/me'),
  },

  health: () => request<Health>('/api/health'),

  settings: {
    get: () => request<AppSettings>('/api/settings'),
    update: (patch: SettingsPatch) =>
      request<AppSettings>('/api/settings', {
        method: 'PUT',
        body: JSON.stringify(patch),
      }),
    removeSecret: (key: string) =>
      request<AppSettings>(`/api/settings/secret/${encodeURIComponent(key)}`, {
        method: 'DELETE',
      }),
    test: (provider: 'openrouter' | 'elevenlabs' | 'pi') =>
      request<ConnectionTestResult>(`/api/settings/test/${provider}`, {
        method: 'POST',
      }),
  },

  projects: {
    list: () => request<Project[]>('/api/projects'),
    create: (name: string, parent?: string) =>
      request<Project>(
        '/api/projects',
        json(parent ? { name, parent } : { name }),
      ),
    /** Open an existing directory in place. Nothing is copied or uploaded. */
    open: (path: string, name?: string) =>
      request<Project>('/api/projects/open', json(name ? { path, name } : { path })),
    upload: (file: File, name?: string) => {
      const form = new FormData()
      form.append('file', file)
      if (name) form.append('name', name)
      return request<Project>('/api/projects/upload', {
        method: 'POST',
        body: form,
      })
    },
    get: (id: string) => request<Project>(`/api/projects/${id}`),
    /** `removeFiles` defaults to true for managed projects, false for opened ones. */
    remove: (id: string, removeFiles?: boolean) =>
      request<void>(
        `/api/projects/${id}${
          removeFiles === undefined ? '' : `?remove_files=${removeFiles}`
        }`,
        { method: 'DELETE' },
      ),
    summary: (id: string) =>
      request<ProjectSummary>(`/api/projects/${id}/summary`),
    tree: (id: string, refresh = false) =>
      request<ProjectTree>(
        `/api/projects/${id}/tree${refresh ? '?refresh=true' : ''}`,
      ),
    config: (id: string) => request<ProjectConfig>(`/api/projects/${id}/config`),
    updateConfig: (id: string, patch: ProjectConfig) =>
      request<ProjectConfig>(`/api/projects/${id}/config`, {
        method: 'PUT',
        body: JSON.stringify(patch),
      }),
    memory: {
      list: (id: string, limit = 200) =>
        request<MemoryEntry[]>(`/api/projects/${id}/memory?limit=${limit}`),
      add: (id: string, entry: MemoryCreate) =>
        request<MemoryEntry>(`/api/projects/${id}/memory`, json(entry)),
      remove: (id: string, entryId: string) =>
        request<void>(`/api/projects/${id}/memory/${entryId}`, {
          method: 'DELETE',
        }),
    },
  },

  fs: {
    /** List sub-directories for the Open Project browser. */
    list: (path?: string) =>
      request<FsListing>(
        `/api/fs/list${path ? `?path=${encodeURIComponent(path)}` : ''}`,
      ),
  },

  pi: {
    status: () => request<PiStatus>('/api/pi/status'),
    runtime: (verify = false) =>
      request<PiRuntime>(`/api/pi/runtime${verify ? '?verify=true' : ''}`),
    installRuntime: (force = false) =>
      request<PiInstallResult>(
        `/api/pi/runtime/install?verify=true${force ? '&force=true' : ''}`,
        { method: 'POST' },
      ),
    verifyRuntime: () =>
      request<PiRuntime>('/api/pi/runtime/verify', { method: 'POST' }),
    providers: () => request<PiProvider[]>('/api/pi/providers'),
    models: (provider?: string, refresh = false) => {
      const params = new URLSearchParams()
      if (provider) params.set('provider', provider)
      if (refresh) params.set('refresh', 'true')
      const query = params.toString()
      return request<PiModel[]>(`/api/pi/models${query ? `?${query}` : ''}`)
    },
    refreshModels: () =>
      request<{ ok: boolean; message: string; output: string | null }>(
        '/api/pi/models/refresh',
        { method: 'POST' },
      ),
    auth: (provider: string) =>
      request<PiAuthStatus>(`/api/pi/providers/${encodeURIComponent(provider)}/auth`),
    saveCredential: (provider: string, apiKey: string) =>
      request<PiAuthStatus>(
        `/api/pi/providers/${encodeURIComponent(provider)}/credential`,
        { method: 'PUT', body: JSON.stringify({ api_key: apiKey }) },
      ),
    deleteCredential: (provider: string) =>
      request<PiAuthStatus>(
        `/api/pi/providers/${encodeURIComponent(provider)}/credential`,
        { method: 'DELETE' },
      ),
    credentialFromOrchestrator: (provider: string) =>
      request<PiAuthStatus>(
        `/api/pi/providers/${encodeURIComponent(provider)}/credential/from-orchestrator`,
        { method: 'POST' },
      ),
    test: (provider: string, options: { model?: string; deep?: boolean } = {}) => {
      const params = new URLSearchParams()
      if (options.model) params.set('model', options.model)
      if (options.deep) params.set('deep', 'true')
      const query = params.toString()
      return request<ConnectionTestResult>(
        `/api/pi/providers/${encodeURIComponent(provider)}/test${query ? `?${query}` : ''}`,
        { method: 'POST' },
      )
    },
  },

  orchestrator: {
    status: () => request<OrchestratorStatus>('/api/orchestrator/status'),
    config: (patch: { model?: string; enabled?: boolean }) =>
      request<OrchestratorStatus>('/api/orchestrator/config', {
        method: 'PUT',
        body: JSON.stringify(patch),
      }),
    models: (search?: string) =>
      request<OpenRouterModel[]>(
        `/api/orchestrator/models${search ? `?search=${encodeURIComponent(search)}` : ''}`,
      ),
    test: (options: { model?: string; deep?: boolean } = {}) => {
      const params = new URLSearchParams()
      if (options.model) params.set('model', options.model)
      if (options.deep === false) params.set('deep', 'false')
      const query = params.toString()
      return request<ConnectionTestResult>(
        `/api/orchestrator/test${query ? `?${query}` : ''}`,
        { method: 'POST' },
      )
    },
  },

  orchestration: {
    get: (projectId: string) =>
      request<OrchestrationView>(`/api/projects/${projectId}/orchestration`),
    plan: (projectId: string, instruction: string) =>
      request<OrchestrationView>(`/api/projects/${projectId}/orchestration/plan`, {
        method: 'POST',
        body: JSON.stringify({ instruction }),
      }),
    note: (projectId: string, instruction: string) =>
      request<OrchestrationView>(`/api/projects/${projectId}/orchestration/notes`, {
        method: 'POST',
        body: JSON.stringify({ instruction }),
      }),
    skip: (projectId: string, planId: string) =>
      request<OrchestrationView>(
        `/api/projects/${projectId}/orchestration/queue/${planId}/skip`,
        { method: 'POST' },
      ),
    remove: (projectId: string, planId: string) =>
      request<OrchestrationView>(
        `/api/projects/${projectId}/orchestration/queue/${planId}`,
        { method: 'DELETE' },
      ),
    advance: (projectId: string) =>
      request<{ started: boolean; reason?: string; title?: string }>(
        `/api/projects/${projectId}/orchestration/advance`,
        { method: 'POST' },
      ),
  },

  files: {
    limits: (projectId: string) =>
      request<FileLimits>(`/api/projects/${projectId}/files/limits`),
    read: (projectId: string, path: string) =>
      request<FileContent>(
        `/api/projects/${projectId}/files?path=${encodeURIComponent(path)}`,
      ),
    write: (projectId: string, path: string, content: string, overwrite = true) =>
      request<FileContent>(`/api/projects/${projectId}/files`, {
        method: 'PUT',
        body: JSON.stringify({ path, content, overwrite }),
      }),
    upload: (projectId: string, file: File, directory = '', overwrite = true) => {
      const form = new FormData()
      form.append('file', file)
      form.append('directory', directory)
      form.append('overwrite', String(overwrite))
      return request<FileContent>(`/api/projects/${projectId}/files/upload`, {
        method: 'POST',
        body: form,
      })
    },
  },

  checks: {
    status: () => request<ChecksStatus>('/api/checks/status'),
    run: (projectId: string) =>
      request<CheckResult>(`/api/projects/${projectId}/checks`, { method: 'POST' }),
  },

  tasks: {
    list: (projectId?: string) =>
      request<Task[]>(
        `/api/tasks${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''}`,
      ),
    get: (id: string) => request<TaskDetail>(`/api/tasks/${id}`),
    events: (id: string) => request<AppEvent[]>(`/api/tasks/${id}/events`),
    create: (projectId: string, instruction: string) =>
      request<Task>('/api/tasks', json({ project_id: projectId, instruction })),
    cancel: (id: string) =>
      request<Task>(`/api/tasks/${id}/cancel`, { method: 'POST' }),
    steer: (id: string, instruction: string) =>
      request<Task>(
        `/api/tasks/${id}/steer`,
        json({ instruction }),
      ),
  },

  messages: {
    list: (projectId: string, limit = 200) =>
      request<Message[]>(
        `/api/projects/${projectId}/messages?limit=${limit}`,
      ),
    send: (projectId: string, content: string) =>
      request<MessageDispatchResult>(
        `/api/projects/${projectId}/messages`,
        json({ content }),
      ),
  },
}
