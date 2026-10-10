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
    created_at: datetime
    updated_at: datetime
    file_count: int = 0


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


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
