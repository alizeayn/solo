"""Pydantic schemas: the public API contract.

Secrets are never represented by their real value in an outbound schema; only
``configured`` + ``masked`` status is exposed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class SetupRequest(BaseModel):
    username: str = Field(default="admin", min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=256)


class AuthStatus(BaseModel):
    initialized: bool
    authenticated: bool
    username: str | None = None


# --------------------------------------------------------------------------- #
# Account
# --------------------------------------------------------------------------- #
class AccountOut(BaseModel):
    username: str
    role: str = "owner"
    created_at: str | None = None
    active_sessions: int = 1
    has_session: bool = True


class UsernameUpdate(BaseModel):
    new_username: str = Field(min_length=3, max_length=64)
    #: Required even though the caller is already authenticated.
    current_password: str = Field(min_length=1, max_length=256)


class PasswordUpdate(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
class SecretStatus(BaseModel):
    configured: bool = False
    masked: str | None = None


class ProviderStatus(BaseModel):
    """Connection-relevant status for one provider, without leaking secrets."""

    name: str
    configured: bool
    detail: str | None = None


class SettingsOut(BaseModel):
    openrouter_api_key: SecretStatus
    elevenlabs_api_key: SecretStatus
    openrouter_model: str | None = None
    elevenlabs_agent_id: str | None = None
    elevenlabs_tts_voice_id: str | None = None
    #: Text-to-speech model id (e.g. ``eleven_flash_v2_5``).
    elevenlabs_model_id: str | None = None
    #: Speech-to-text model id (e.g. ``scribe_v2``).
    elevenlabs_stt_model_id: str | None = None
    #: Read-only: the name of the selected voice, for display.
    elevenlabs_voice_name: str | None = None
    pi_provider: str | None = None
    pi_model: str | None = None
    pi_base_url: str | None = None
    pi_thinking_level: str | None = None
    pi_approve_project: bool = False
    pi_reuse_openrouter_key: bool = False
    orchestrator_enabled: bool = True
    checks_enabled: bool = True
    voice_enabled: bool = True
    progress_speech_enabled: bool = True
    pi_version: str | None = None
    pi_rpc_available: bool = False
    #: ``dark``, ``light`` or ``system``.
    theme: str = "dark"


class SettingsUpdate(BaseModel):
    """Partial update. ``None`` means "leave unchanged"; empty string clears."""

    openrouter_api_key: str | None = None
    elevenlabs_api_key: str | None = None
    openrouter_model: str | None = None
    elevenlabs_agent_id: str | None = None
    elevenlabs_tts_voice_id: str | None = None
    elevenlabs_model_id: str | None = None
    elevenlabs_stt_model_id: str | None = None
    pi_provider: str | None = None
    pi_model: str | None = None
    pi_base_url: str | None = None
    pi_thinking_level: str | None = None
    pi_approve_project: bool | None = None
    pi_reuse_openrouter_key: bool | None = None
    orchestrator_enabled: bool | None = None
    checks_enabled: bool | None = None
    voice_enabled: bool | None = None
    progress_speech_enabled: bool | None = None
    theme: str | None = None


class ConnectionTestResult(BaseModel):
    ok: bool
    message: str
    detail: str | None = None
    #: ``verified`` (a real request succeeded), ``configured`` (credentials
    #: present but not exercised), ``not_configured``, ``failed`` or ``skipped``.
    state: str | None = None
    provider: str | None = None
    model: str | None = None
    latency_ms: int | None = None


# --------------------------------------------------------------------------- #
# Pi Agent configuration
# --------------------------------------------------------------------------- #
class PiRuntimeOut(BaseModel):
    available: bool
    version: str | None = None
    executable: str | None = None
    agent_dir: str | None = None
    detail: str | None = None
    #: True when Solo's own installation is present and runnable.
    installed: bool = False
    #: True only when the runtime was actually started and answered a command.
    verified: bool = False
    #: ``managed`` (Solo's own copy), ``external`` (an explicit override), ``none``.
    source: str = "none"
    #: True when ``source == "managed"`` — i.e. the host's Pi is not involved.
    isolated: bool = False
    node: str | None = None
    runtime_dir: str | None = None
    installed_at: str | None = None
    last_error: str | None = None


class PiInstallOut(BaseModel):
    ok: bool
    message: str
    detail: str | None = None
    version: str | None = None
    duration_ms: int = 0
    output: str | None = None
    runtime: PiRuntimeOut | None = None


class PiProviderOut(BaseModel):
    id: str
    label: str
    env_var: str | None = None
    configured: bool = False
    auth_type: str | None = None
    #: ``saved``, ``environment``, ``oauth`` or ``none``.
    source: str = "none"
    model_count: int = 0
    model_count_known: bool = True
    in_catalog: bool = False


class PiModelOut(BaseModel):
    id: str
    name: str
    provider: str
    reasoning: bool = False
    context_window: int | None = None
    max_tokens: int | None = None
    input_modalities: list[str] = Field(default_factory=list)
    cost: dict[str, Any] | None = None


class PiCredentialIn(BaseModel):
    api_key: str = Field(min_length=1, max_length=4096)


class PiAuthOut(BaseModel):
    provider: str
    status: str
    ready: bool = False
    auth_type: str | None = None
    reason: str | None = None
    detail: str | None = None


class PiStatusOut(BaseModel):
    runtime: PiRuntimeOut
    #: ``pi``, ``mock`` — which backend coding tasks will use.
    backend: str
    provider: str | None = None
    model: str | None = None
    thinking_level: str | None = None
    approve_project: bool = False
    minimal_harness: bool = True
    agent_dir: str | None = None
    auth_file: str | None = None
    runtime_dir: str | None = None
    node: str | None = None
    configured_providers: list[str] = Field(default_factory=list)
    sessions: list[dict[str, Any]] = Field(default_factory=list)


class PiCatalogRefreshOut(BaseModel):
    ok: bool
    message: str
    output: str | None = None


# --------------------------------------------------------------------------- #
# Orchestrator (OpenRouter)
# --------------------------------------------------------------------------- #
class OrchestratorStatusOut(BaseModel):
    enabled: bool = True
    configured: bool = False
    has_key: bool = False
    model: str | None = None
    key_masked: str | None = None
    call_count: int = 0
    failure_count: int = 0
    last_error: str | None = None
    last_latency_ms: int | None = None
    last_model: str | None = None


class OrchestratorConfigIn(BaseModel):
    model: str | None = None
    enabled: bool | None = None


class OpenRouterModelOut(BaseModel):
    id: str
    name: str
    context_length: int | None = None
    supports_structured_output: bool = False
    pricing: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Orchestration state (project-scoped)
# --------------------------------------------------------------------------- #
class PlannedTaskOut(BaseModel):
    id: str
    title: str
    instruction: str
    priority: int = 50
    depends_on: list[str] = Field(default_factory=list)
    status: str = "pending"
    source: str = "user"
    task_id: str | None = None
    note: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class OrchestrationStateOut(BaseModel):
    summary: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)


class OrchestrationPlanIn(BaseModel):
    instruction: str = Field(min_length=1, max_length=8000)


# --------------------------------------------------------------------------- #
# Project files (Writing panel and uploads)
# --------------------------------------------------------------------------- #
class FileContentOut(BaseModel):
    path: str
    content: str = ""
    size: int = 0
    truncated: bool = False
    #: True when the file is not valid UTF-8 text; `content` is then empty.
    binary: bool = False


class FileWriteIn(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    content: str = Field(default="", max_length=2_000_000)
    #: False makes the write fail when the file already exists.
    overwrite: bool = True


# --------------------------------------------------------------------------- #
# Static checks
# --------------------------------------------------------------------------- #
class DiagnosticOut(BaseModel):
    file: str
    line: int
    column: int
    severity: str
    message: str
    rule: str | None = None


class CheckResultOut(BaseModel):
    tool: str
    outcome: str
    summary: str
    error_count: int = 0
    warning_count: int = 0
    files_checked: int = 0
    duration_ms: int = 0
    command: str | None = None
    output: str | None = None
    passed: bool = False
    diagnostics: list[DiagnosticOut] = Field(default_factory=list)


class ChecksStatusOut(BaseModel):
    enabled: bool
    available: bool
    tool: str
    executable: str | None = None
    detail: str | None = None


# --------------------------------------------------------------------------- #
# Projects
# --------------------------------------------------------------------------- #
class ProjectOut(ORMModel):
    id: str
    name: str
    slug: str
    source: str
    status: str
    #: ``managed`` (created inside Solo's workspaces directory) or ``external``
    #: (an existing directory opened in place).
    location: str = "managed"
    #: Absolute path of the project root, filled in by the API layer.
    root: str | None = None
    #: Directory name holding Solo state inside the project root.
    metadata_dir: str = ".solo"
    is_managed: bool = True
    created_at: datetime
    updated_at: datetime
    file_count: int = 0


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    #: Optional parent directory. When omitted, the project is created inside
    #: Solo's managed workspaces directory.
    parent: str | None = Field(default=None, max_length=4096)


class ProjectOpen(BaseModel):
    """Open an existing directory on this machine, in place."""

    path: str = Field(min_length=1, max_length=4096)
    name: str | None = Field(default=None, max_length=200)


# --------------------------------------------------------------------------- #
# Project state store: tree, memory, configuration
# --------------------------------------------------------------------------- #
class TreeNode(BaseModel):
    """One node of the structured project state tree.

    Extra keys are preserved because node shapes differ by ``kind``
    (file, directory, task, memory, session, group, project).
    """

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    kind: str
    children: list["TreeNode"] = Field(default_factory=list)


class ProjectTreeOut(BaseModel):
    version: int
    generated_at: str
    truncated: bool = False
    project: dict[str, Any] = Field(default_factory=dict)
    root: TreeNode


class MemoryEntryOut(BaseModel):
    id: str
    kind: str
    text: str
    tags: list[str] = Field(default_factory=list)
    source: str = "user"
    task_id: str | None = None
    created_at: str | None = None


class MemoryCreate(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    kind: str = Field(default="note", max_length=32)
    tags: list[str] = Field(default_factory=list, max_length=16)


class ProjectSummaryOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    project_id: str
    name: str
    location: str
    root: str
    metadata_dir: str
    metadata_exists: bool
    file_count: int
    directory_count: int
    task_count: int
    session_count: int
    memory_count: int
    task_status_counts: dict[str, int] = Field(default_factory=dict)
    tree_generated_at: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class ProjectConfigUpdate(BaseModel):
    """Partial per-project configuration; deep-merged into the stored config."""

    model_config = ConfigDict(extra="allow")

    tree: dict[str, Any] | None = None
    memory: dict[str, Any] | None = None
    sessions: dict[str, Any] | None = None
    state: dict[str, Any] | None = None
    agent: dict[str, Any] | None = None


# --------------------------------------------------------------------------- #
# Filesystem browser (Open Project)
# --------------------------------------------------------------------------- #
class FsEntry(BaseModel):
    name: str
    path: str
    hidden: bool = False
    #: True when the directory already contains Solo project metadata.
    is_project: bool = False


class FsListing(BaseModel):
    path: str
    parent: str | None = None
    roots: list[str] = Field(default_factory=list)
    entries: list[FsEntry] = Field(default_factory=list)
    truncated: bool = False


# --------------------------------------------------------------------------- #
# Messages
# --------------------------------------------------------------------------- #
class MessageOut(ORMModel):
    id: str
    conversation_id: str
    role: str
    content: str
    task_id: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=32_000)
    conversation_id: str | None = None


class MessageDispatchResult(BaseModel):
    """Result envelope for a routed user message."""

    intent: str
    message: MessageOut
    task_id: str | None = None
    #: ``orchestrator-model`` when the OpenRouter model classified the message,
    #: ``rules`` when the deterministic fallback did.
    classified_by: str = "rules"


# --------------------------------------------------------------------------- #
# Tasks & events
# --------------------------------------------------------------------------- #
class TaskFileOut(ORMModel):
    path: str
    change_type: str
    created_at: datetime


class TaskOut(ORMModel):
    id: str
    project_id: str
    conversation_id: str | None = None
    parent_task_id: str | None = None
    task_type: str
    status: str
    instruction: str
    progress_summary: str | None = None
    result_summary: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class TaskDetailOut(TaskOut):
    files: list[TaskFileOut] = Field(default_factory=list)


class TaskCreate(BaseModel):
    project_id: str
    instruction: str = Field(min_length=1, max_length=32_000)


class EventOut(ORMModel):
    id: int
    task_id: str | None = None
    project_id: str | None = None
    type: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    database: bool
    workspaces_dir: bool
    coding_agent: str
    pi_version: str | None = None
    #: True when coding tasks run through Solo's own Pi Agent runtime.
    pi_isolated: bool = False
    #: Database schema version after startup migrations.
    schema_version: int = 0


class WsEnvelope(BaseModel):
    """Messages pushed over the application WebSocket."""

    channel: str  # event | task | message | ready | error
    payload: dict[str, Any]
