/**
 * Frontend domain types.
 *
 * These mirror the backend Pydantic schemas in `backend/app/schemas.py` and the
 * enum values in `backend/app/domain.py`. Keep them in sync when the API
 * contract changes.
 */

export type TaskStatus =
  | 'QUEUED'
  | 'RUNNING'
  | 'WAITING_FOR_INPUT'
  | 'PAUSE_REQUESTED'
  | 'PAUSED'
  | 'CANCEL_REQUESTED'
  | 'CANCELLED'
  | 'COMPLETED'
  | 'FAILED'
  | 'RECOVERY_REQUIRED'

export type TaskType = 'CODING' | 'QUESTION' | 'CONTEXT_LOOKUP'

export type Intent =
  | 'CHAT_OR_EXPLAIN'
  | 'STEER_ACTIVE_TASK'
  | 'STOP_ACTIVE_TASK'
  | 'START_CODING_TASK'
  | 'NEEDS_CLARIFICATION'

export type MessageRole = 'user' | 'assistant' | 'system'

export interface AuthStatus {
  initialized: boolean
  authenticated: boolean
  username: string | null
}

export interface SecretStatus {
  configured: boolean
  masked: string | null
}

export interface AppSettings {
  openrouter_api_key: SecretStatus
  elevenlabs_api_key: SecretStatus
  openrouter_model: string | null
  elevenlabs_agent_id: string | null
  elevenlabs_tts_voice_id: string | null
  pi_provider: string | null
  pi_model: string | null
  pi_base_url: string | null
  pi_thinking_level: string | null
  pi_approve_project: boolean
  pi_reuse_openrouter_key: boolean
  orchestrator_enabled: boolean
  checks_enabled: boolean
  voice_enabled: boolean
  progress_speech_enabled: boolean
  pi_version: string | null
  pi_rpc_available: boolean
}

export type SettingsPatch = Partial<{
  openrouter_api_key: string
  elevenlabs_api_key: string
  openrouter_model: string
  elevenlabs_agent_id: string
  elevenlabs_tts_voice_id: string
  pi_provider: string
  pi_model: string
  pi_base_url: string
  pi_thinking_level: string
  pi_approve_project: boolean
  pi_reuse_openrouter_key: boolean
  orchestrator_enabled: boolean
  checks_enabled: boolean
  voice_enabled: boolean
  progress_speech_enabled: boolean
}>

export interface ConnectionTestResult {
  ok: boolean
  message: string
  detail: string | null
  /** verified | configured | not_configured | failed | skipped */
  state?: string | null
  provider?: string | null
  model?: string | null
  latency_ms?: number | null
}

/* ------------------------------------------------------------------ */
/* Pi Agent                                                            */
/* ------------------------------------------------------------------ */
export interface PiRuntime {
  available: boolean
  version: string | null
  executable: string | null
  agent_dir: string | null
  detail: string | null
}

export interface PiStatus {
  runtime: PiRuntime
  /** `pi` or `mock` — which backend coding tasks will use. */
  backend: string
  provider: string | null
  model: string | null
  thinking_level: string | null
  approve_project: boolean
  minimal_harness: boolean
  agent_dir: string | null
  auth_file: string | null
  configured_providers: string[]
  sessions: PiSession[]
}

export interface PiSession {
  cwd: string
  running: boolean
  busy: boolean
  pid: number | null
  provider: string | null
  model: string | null
  uptime: number
  last_stderr: string
}

export interface PiProvider {
  id: string
  label: string
  env_var: string | null
  configured: boolean
  auth_type: string | null
  /** saved | environment | oauth | none */
  source: string
  model_count: number
  model_count_known: boolean
  in_catalog: boolean
}

export interface PiModel {
  id: string
  name: string
  provider: string
  reasoning: boolean
  context_window: number | null
  max_tokens: number | null
  input_modalities: string[]
  cost: Record<string, number> | null
}

export interface PiAuthStatus {
  provider: string
  status: string
  ready: boolean
  auth_type: string | null
  reason: string | null
  detail: string | null
}

/* ------------------------------------------------------------------ */
/* Orchestrator                                                        */
/* ------------------------------------------------------------------ */
export interface OrchestratorStatus {
  enabled: boolean
  configured: boolean
  has_key: boolean
  model: string | null
  key_masked: string | null
  call_count: number
  failure_count: number
  last_error: string | null
  last_latency_ms: number | null
  last_model: string | null
}

export interface OpenRouterModel {
  id: string
  name: string
  context_length: number | null
  supports_structured_output: boolean
  pricing: Record<string, unknown>
}

/* ------------------------------------------------------------------ */
/* Orchestration state                                                 */
/* ------------------------------------------------------------------ */
export interface PlannedTask {
  id: string
  title: string
  instruction: string
  priority: number
  depends_on: string[]
  status: 'pending' | 'running' | 'done' | 'failed' | 'skipped'
  source: string
  task_id: string | null
  note: string | null
  created_at: string | null
  updated_at: string | null
}

export interface OrchestrationView {
  summary: {
    version?: number
    project_id?: string
    revision?: number
    active_task_id?: string | null
    active_plan_id?: string | null
    queue_size?: number
    status_counts?: Record<string, number>
    pending_notes?: number
    updated_at?: string
    next?: PlannedTask | null
  }
  state: {
    version?: number
    project_id?: string
    revision?: number
    active_task_id?: string | null
    active_plan_id?: string | null
    queue?: PlannedTask[]
    notes?: OrchestrationNote[]
    updated_at?: string
  }
}

export interface OrchestrationNote {
  id: string
  text: string
  kind: string
  task_id: string | null
  applied: string | null
  created_at: string
}

/* ------------------------------------------------------------------ */
/* Static checks                                                       */
/* ------------------------------------------------------------------ */
export interface Diagnostic {
  file: string
  line: number
  column: number
  severity: string
  message: string
  rule: string | null
}

export interface CheckResult {
  tool: string
  outcome: 'passed' | 'failed' | 'error' | 'skipped'
  summary: string
  error_count: number
  warning_count: number
  files_checked: number
  duration_ms: number
  command: string | null
  output: string | null
  passed: boolean
  diagnostics: Diagnostic[]
}

export interface ChecksStatus {
  enabled: boolean
  available: boolean
  tool: string
  executable: string | null
  detail: string | null
}

export interface Health {
  status: 'ok' | 'degraded'
  version: string
  database: boolean
  workspaces_dir: boolean
  coding_agent: string
  pi_version: string | null
}

export interface Project {
  id: string
  name: string
  slug: string
  source: string
  status: string
  /** `managed` = created by Solo; `external` = an existing directory opened in place. */
  location: 'managed' | 'external'
  /** Absolute path of the project root on the machine running Solo. */
  root: string | null
  /** Directory name holding Solo state inside the project root (e.g. `.solo`). */
  metadata_dir: string
  is_managed: boolean
  created_at: string
  updated_at: string
  file_count: number
}

/** One node of the structured project state tree. */
export interface TreeNode {
  id: string
  name: string
  kind: 'project' | 'group' | 'directory' | 'file' | 'task' | 'memory' | 'session'
  children?: TreeNode[]
  path?: string
  size?: number | null
  ext?: string | null
  status?: string
  task_type?: string
  memory_kind?: string
  messages?: number
  ref?: string
  created_at?: string
  updated_at?: string
}

export interface ProjectTree {
  version: number
  generated_at: string
  truncated: boolean
  project: Record<string, unknown>
  root: TreeNode
}

export interface MemoryEntry {
  id: string
  kind: string
  text: string
  tags: string[]
  source: string
  task_id: string | null
  created_at: string | null
}

export interface MemoryCreate {
  text: string
  kind?: string
  tags?: string[]
}

export interface ProjectConfig {
  version?: number
  tree?: { max_depth?: number | null; max_entries?: number | null; exclude?: string[] }
  memory?: { max_entries?: number; auto_capture?: boolean }
  sessions?: { max_sessions?: number }
  state?: { auto_refresh?: boolean }
  agent?: {
    backend?: string | null
    provider?: string | null
    model?: string | null
  }
}

export interface ProjectSummary {
  project_id: string
  name: string
  location: 'managed' | 'external'
  root: string
  metadata_dir: string
  metadata_exists: boolean
  file_count: number
  directory_count: number
  task_count: number
  session_count: number
  memory_count: number
  task_status_counts: Record<string, number>
  tree_generated_at: string | null
  config: ProjectConfig
}

export interface FsEntry {
  name: string
  path: string
  hidden: boolean
  /** True when the directory already contains Solo project metadata. */
  is_project: boolean
}

export interface FsListing {
  path: string
  parent: string | null
  roots: string[]
  entries: FsEntry[]
  truncated: boolean
}

export interface TaskFile {
  path: string
  change_type: string
  created_at: string
}

export interface Task {
  id: string
  project_id: string
  conversation_id: string | null
  parent_task_id: string | null
  task_type: TaskType
  status: TaskStatus
  instruction: string
  progress_summary: string | null
  result_summary: string | null
  error: string | null
  created_at: string
  updated_at: string
  completed_at: string | null
}

export interface TaskDetail extends Task {
  files: TaskFile[]
}

export interface AppEvent {
  id: number
  task_id: string | null
  project_id: string | null
  type: string
  message: string
  data: Record<string, unknown>
  created_at: string
}

export interface Message {
  id: string
  conversation_id: string
  role: MessageRole
  content: string
  task_id: string | null
  meta: Record<string, unknown>
  created_at: string
}

export interface MessageDispatchResult {
  intent: Intent
  message: Message
  task_id: string | null
}

export type ConnectionState = 'connecting' | 'open' | 'closed'

export interface WsEnvelope {
  channel: 'event' | 'task' | 'message' | 'orchestration' | 'ready' | 'error'
  payload: Record<string, unknown>
}

/** Task statuses after which no further transition occurs. */
export const TERMINAL_STATUSES: readonly TaskStatus[] = [
  'COMPLETED',
  'CANCELLED',
  'FAILED',
]

/** Statuses that occupy the project's single active-task slot. */
export const ACTIVE_STATUSES: readonly TaskStatus[] = [
  'QUEUED',
  'RUNNING',
  'WAITING_FOR_INPUT',
  'PAUSE_REQUESTED',
  'PAUSED',
  'CANCEL_REQUESTED',
]

export function isActive(task: Task): boolean {
  return ACTIVE_STATUSES.includes(task.status)
}

export function isTerminal(task: Task): boolean {
  return TERMINAL_STATUSES.includes(task.status)
}
