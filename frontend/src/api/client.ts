/**
 * Typed API client.
 *
 * All requests are same-origin and carry the session cookie
 * (`credentials: 'same-origin'`). Secrets are only ever sent *to* the backend;
 * the backend never returns them.
 */

import type {
  AppEvent,
  AppSettings,
  AuthStatus,
  ConnectionTestResult,
  Health,
  Message,
  MessageDispatchResult,
  Project,
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
    create: (name: string) =>
      request<Project>('/api/projects', json({ name })),
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
    remove: (id: string) =>
      request<void>(`/api/projects/${id}`, { method: 'DELETE' }),
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
