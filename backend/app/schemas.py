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
    pi_provider: str | None = None
    pi_model: str | None = None
    pi_base_url: str | None = None
    pi_reuse_openrouter_key: bool = False
    voice_enabled: bool = True
    progress_speech_enabled: bool = True
    pi_version: str | None = None
    pi_rpc_available: bool = False


class SettingsUpdate(BaseModel):
    """Partial update. ``None`` means "leave unchanged"; empty string clears."""

    openrouter_api_key: str | None = None
    elevenlabs_api_key: str | None = None
    openrouter_model: str | None = None
    elevenlabs_agent_id: str | None = None
    elevenlabs_tts_voice_id: str | None = None
    pi_provider: str | None = None
    pi_model: str | None = None
    pi_base_url: str | None = None
    pi_reuse_openrouter_key: bool | None = None
    voice_enabled: bool | None = None
    progress_speech_enabled: bool | None = None


class ConnectionTestResult(BaseModel):
    ok: bool
    message: str
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


class WsEnvelope(BaseModel):
    """Messages pushed over the application WebSocket."""

    channel: str  # event | task | message | ready | error
    payload: dict[str, Any]
