"""Domain vocabulary shared across the backend.

These enums are the single source of truth for task/event/message states and
are mirrored (by value) in the frontend TypeScript types.
"""

from __future__ import annotations

from enum import Enum


class TaskStatus(str, Enum):
    """Lifecycle states for a task.

    ``WAITING_FOR_INPUT`` etc. are used from Phase 2 onward (real Pi agent).
    """

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
    PAUSE_REQUESTED = "PAUSE_REQUESTED"
    PAUSED = "PAUSED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


#: Statuses after which no further transition happens without a new task.
TERMINAL_STATUSES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED}
)

#: Statuses that occupy the single "active modifying task" slot per project.
ACTIVE_STATUSES: frozenset[TaskStatus] = frozenset(
    {
        TaskStatus.QUEUED,
        TaskStatus.RUNNING,
        TaskStatus.WAITING_FOR_INPUT,
        TaskStatus.PAUSE_REQUESTED,
        TaskStatus.PAUSED,
        TaskStatus.CANCEL_REQUESTED,
    }
)


class TaskType(str, Enum):
    CODING = "CODING"
    QUESTION = "QUESTION"
    CONTEXT_LOOKUP = "CONTEXT_LOOKUP"


class Intent(str, Enum):
    """Classification of an inbound user message."""

    CHAT_OR_EXPLAIN = "CHAT_OR_EXPLAIN"
    STEER_ACTIVE_TASK = "STEER_ACTIVE_TASK"
    STOP_ACTIVE_TASK = "STOP_ACTIVE_TASK"
    START_CODING_TASK = "START_CODING_TASK"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"


class EventType(str, Enum):
    """Normalised application event vocabulary.

    Adapters translate provider-specific protocol records into these values so
    the rest of the app never parses raw agent output.
    """

    TASK_CREATED = "task.created"
    TASK_STATUS_CHANGED = "task.status_changed"
    RUN_STARTED = "run.started"
    RUN_FINISHED = "run.finished"
    TOOL_STARTED = "tool.started"
    TOOL_UPDATED = "tool.updated"
    TOOL_FINISHED = "tool.finished"
    FILE_CHANGED = "file.changed"
    TEST_RESULT = "test.result"
    CHECK_RESULT = "check.result"
    PROGRESS_SUMMARY = "progress.summary"
    STATE_UPDATED = "state.updated"
    ERROR = "error"
    MESSAGE_RECEIVED = "message.received"
    ASSISTANT_MESSAGE = "assistant.message"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ProjectSource(str, Enum):
    CREATED = "created"
    OPENED = "opened"
    IMPORTED = "imported"


class ProjectLocation(str, Enum):
    """Where a project's files live."""

    #: Created by Solo inside the application-managed workspaces directory.
    MANAGED = "managed"
    #: An existing directory on disk, opened in place and never copied.
    EXTERNAL = "external"


class MemoryKind(str, Enum):
    """Category of a project memory entry."""

    NOTE = "note"
    DECISION = "decision"
    FACT = "fact"
    TODO = "todo"


class PlannedTaskStatus(str, Enum):
    """Lifecycle of a queued unit of orchestrator work."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class Theme(str, Enum):
    """Appearance preference. ``system`` follows the operating system."""

    DARK = "dark"
    LIGHT = "light"
    SYSTEM = "system"


class CheckOutcome(str, Enum):
    """Result of a static-analysis run."""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


#: Settings keys recognised by the application (grouped for the UI).
SECRET_SETTING_KEYS: frozenset[str] = frozenset(
    {
        "openrouter_api_key",
        # The Orchestrator's second provider. Stored encrypted like the first:
        # which provider is active must not change how well a key is protected.
        "opencode_go_api_key",
        "elevenlabs_api_key",
    }
)

PLAIN_SETTING_KEYS: frozenset[str] = frozenset(
    {
        "openrouter_model",
        "opencode_go_model",
        # Which provider the Orchestrator reasons with.
        "orchestrator_provider",
        "elevenlabs_agent_id",
        "elevenlabs_tts_voice_id",
        "elevenlabs_model_id",
        "elevenlabs_stt_model_id",
        "pi_provider",
        "pi_model",
        "pi_base_url",
        "pi_thinking_level",
        "pi_approve_project",
        "pi_reuse_openrouter_key",
        "orchestrator_enabled",
        "checks_enabled",
        "theme",
        "voice_enabled",
        "progress_speech_enabled",
    }
)

ALL_SETTING_KEYS: frozenset[str] = SECRET_SETTING_KEYS | PLAIN_SETTING_KEYS
