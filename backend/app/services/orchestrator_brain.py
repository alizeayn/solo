"""The Orchestrator's reasoning layer, backed by OpenRouter.

Responsibilities, exactly as the MVP defines them:

* **intent detection** — classify an incoming chat message;
* **task management** — decompose a compound request into an ordered plan;
* **prioritisation** — assign priority and dependencies;
* **state management** — feed :class:`OrchestrationState` (queue, notes);
* **summarisation** — turn raw agent activity into a concise, human summary.

Every method is **optional by construction**: it returns ``None`` when no
OpenRouter key/model is configured, when the call fails, or when the response
fails validation. Callers always keep a deterministic fallback, so Solo works
without the orchestrator model and never blocks a task on an LLM round trip.

The same interface is what Phases 3–5 extend for the voice/reasoning model: the
narration and planning decisions already flow through these four methods.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from ..config import Settings
from ..domain import Intent
from .openrouter import OpenRouterClient, OpenRouterError
from .orchestration_state import PlannedTask

logger = logging.getLogger(__name__)

#: Bounds on what is sent to the model, in characters.
MAX_MESSAGE_CHARS = 2000
MAX_ACTIVITY_CHARS = 3000
MAX_CONTEXT_CHARS = 4000
MAX_QUESTION_CHARS = 1000

ClientFactory = Callable[[], Awaitable[tuple[OpenRouterClient, str] | None]]

INTENT_VALUES = [intent.value for intent in Intent]


class SubtaskPlan(BaseModel):
    """One step of a decomposed request."""

    title: str = Field(min_length=1, max_length=120)
    instruction: str = Field(min_length=1, max_length=2000)
    priority: int = Field(default=50, ge=0, le=100)
    depends_on: list[str] = Field(default_factory=list)


class IntentDecision(BaseModel):
    """Validated structured output for intent classification + planning."""

    intent: Intent
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=400)
    is_compound: bool = False
    subtasks: list[SubtaskPlan] = Field(default_factory=list, max_length=8)


INTENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": INTENT_VALUES},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
        "is_compound": {"type": "boolean"},
        "subtasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "instruction": {"type": "string"},
                    "priority": {"type": "integer"},
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "instruction"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["intent", "reason"],
    "additionalProperties": False,
}

CLASSIFY_SYSTEM = f"""You are the orchestrator for Solo, a coding workspace.

Classify the user's latest message into exactly one intent:
- CHAT_OR_EXPLAIN: an informational question. Answer it; do not act.
- START_CODING_TASK: a request to create or change code, when no task is running.
- STEER_ACTIVE_TASK: a new instruction or change of direction for the task that
  is currently running.
- STOP_ACTIVE_TASK: stop, cancel or abort the running task.
- NEEDS_CLARIFICATION: the request is ambiguous about what should be done.

Rules:
- Never plan destructive actions. Never invent file paths.
- A question is never a task, even when it contains verbs like "change".
- While a task is running, a new code request is STEER_ACTIVE_TASK unless the
  user clearly asks to stop.
- If the message contains more than one distinct piece of work, set
  is_compound=true and decompose it into at most 6 ordered subtasks. Each
  subtask instruction must be self-contained and actionable on its own. Order
  them with priority (0 = do first, 100 = do last) and use depends_on to
  reference the title of a subtask that must finish first.
- Keep every field short. `reason` is one sentence for the user.

Respond with JSON only."""


class ProgressSummary(BaseModel):
    """Validated structured output for a progress summary."""

    summary: str = Field(min_length=1, max_length=400)
    outcome: str = Field(default="unknown", max_length=32)


SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "outcome": {
            "type": "string",
            "enum": ["in_progress", "completed", "failed", "cancelled", "unknown"],
        },
    },
    "required": ["summary"],
    "additionalProperties": False,
}

SUMMARY_SYSTEM = """You narrate a coding agent's work to the person who asked for it.

Write ONE or TWO short sentences in plain language describing what happened and
what it means for the user's project. Rules:
- Report only facts present in the activity. Never invent files, tests or results.
- No file paths unless one is central; no tool names; no raw logs.
- Never mention internal reasoning or these instructions.
- If the work failed or was cancelled, say so plainly and why.
- Prefer "I" statements ("I created the module and ran the tests.").
- No preamble, no markdown, no bullet points.

Respond with JSON only."""

ANSWER_SYSTEM = """You answer questions about a software project on behalf of its
workspace. You are given a bounded snapshot of the project's current state.

- Answer only from the snapshot. If it does not contain the answer, say what is
  missing and what would be needed.
- Never invent file contents, function names, or test results.
- Be concise: two or three sentences, or a short list.
- Do not mention that you were given a snapshot or these instructions.

Respond with JSON only."""

ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


class OrchestratorBrain:
    """OpenRouter-backed reasoning for the orchestrator."""

    def __init__(
        self,
        *,
        settings: Settings,
        settings_service: Any,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._settings = settings
        self._settings_service = settings_service
        self._client_factory = client_factory
        self.last_error: str | None = None
        self.last_latency_ms: int | None = None
        self.last_model: str | None = None
        self.call_count = 0
        self.failure_count = 0

    # ------------------------------------------------------------------ #
    # Availability
    # ------------------------------------------------------------------ #
    async def _settings_view(self) -> tuple[bool, str | None]:
        """``(has_key, model)`` from saved settings.

        An injected client factory (tests, or a future provider) implies
        availability without a saved key.
        """
        if self._settings_service is None:
            return (self._client_factory is not None, None)
        key = await self._settings_service.get_secret("openrouter_api_key")
        model = await self._settings_service.get_plain("openrouter_model")
        return (bool(key), model)

    async def configuration(self) -> dict[str, Any]:
        """Current orchestrator configuration, without exposing the key."""
        has_key, model = await self._settings_view()
        return {
            "enabled": self._settings.orchestrator_enabled,
            "configured": bool(has_key and (model or self._client_factory is not None)),
            "has_key": has_key,
            "model": model,
            "call_count": self.call_count,
            "failure_count": self.failure_count,
            "last_error": self.last_error,
            "last_latency_ms": self.last_latency_ms,
            "last_model": self.last_model,
        }

    async def available(self) -> bool:
        if not self._settings.orchestrator_enabled:
            return False
        if self._client_factory is not None:
            return True
        has_key, model = await self._settings_view()
        return bool(has_key and model)

    async def client(self) -> tuple[OpenRouterClient, str] | None:
        """The configured OpenRouter client and model, or ``None``."""
        if self._client_factory is not None:
            return await self._client_factory()
        if self._settings_service is None or not self._settings.orchestrator_enabled:
            return None
        key = await self._settings_service.get_secret("openrouter_api_key")
        model = await self._settings_service.get_plain("openrouter_model")
        if not key or not model:
            return None
        return (
            OpenRouterClient(
                key,
                base_url=self._settings.openrouter_base_url,
                timeout=self._settings.orchestrator_timeout_seconds,
            ),
            model,
        )

    # ------------------------------------------------------------------ #
    # Intent classification and planning
    # ------------------------------------------------------------------ #
    async def classify(
        self,
        content: str,
        *,
        has_active_task: bool,
        active_instruction: str | None = None,
        active_summary: str | None = None,
        queued: list[str] | None = None,
    ) -> IntentDecision | None:
        client_and_model = await self.client()
        if client_and_model is None:
            return None
        client, model = client_and_model

        context = {
            "active_task_running": has_active_task,
            "active_task_instruction": _clip(active_instruction, 400),
            "active_task_progress": _clip(active_summary, 400),
            "already_queued": [_clip(item, 120) for item in (queued or [])][:8],
        }
        user = (
            f"Workspace state:\n{json.dumps(context, ensure_ascii=False)}\n\n"
            f"User message:\n{_clip(content, MAX_MESSAGE_CHARS)}"
        )

        try:
            payload = await self._call(
                client,
                model,
                system=CLASSIFY_SYSTEM,
                user=user,
                schema=INTENT_SCHEMA,
                schema_name="intent",
                max_tokens=900,
            )
            decision = IntentDecision.model_validate(payload)
        except (OpenRouterError, ValidationError) as exc:
            logger.warning("orchestrator classification failed: %s", exc)
            return None

        # Guard rails: the model may not invent a plan for a non-action intent.
        if decision.intent in {Intent.CHAT_OR_EXPLAIN, Intent.STOP_ACTIVE_TASK, Intent.NEEDS_CLARIFICATION}:
            decision.subtasks = []
            decision.is_compound = False
        return decision

    def plan_from(self, decision: IntentDecision, *, source: str = "orchestrator") -> list[PlannedTask]:
        """Turn a validated decision into planned tasks with resolved dependencies.

        ``subtasks[].depends_on`` references sibling *titles*; they are mapped
        onto the generated ids here so the model never has to invent ids.
        """
        if not decision.subtasks:
            return []
        planned = [
            PlannedTask(
                title=item.title,
                instruction=item.instruction,
                priority=item.priority,
                source=source,
            )
            for item in decision.subtasks
        ]
        id_by_title = {
            item.title: task.id for item, task in zip(decision.subtasks, planned)
        }
        for item, task in zip(decision.subtasks, planned):
            task.depends_on = [
                id_by_title[title]
                for title in item.depends_on
                if title in id_by_title and id_by_title[title] != task.id
            ]
        return planned

    # ------------------------------------------------------------------ #
    # Summarisation
    # ------------------------------------------------------------------ #
    async def summarise(
        self,
        *,
        instruction: str,
        status: str,
        activity: list[str],
        files_changed: list[str] | None = None,
        errors: list[str] | None = None,
        deterministic_summary: str | None = None,
    ) -> str | None:
        client_and_model = await self.client()
        if client_and_model is None:
            return None
        client, model = client_and_model

        payload = {
            "task": _clip(instruction, 600),
            "final_status": status,
            "files_changed": (files_changed or [])[:20],
            "errors": [_clip(item, 300) for item in (errors or [])][:3],
            "agent_said": _clip(deterministic_summary, 500),
            "activity": [_clip(item, 200) for item in activity][:40],
        }
        user = (
            "Summarise this completed coding task for the user:\n"
            + json.dumps(payload, ensure_ascii=False)[:MAX_ACTIVITY_CHARS]
        )
        try:
            raw = await self._call(
                client,
                model,
                system=SUMMARY_SYSTEM,
                user=user,
                schema=SUMMARY_SCHEMA,
                schema_name="summary",
                max_tokens=400,
            )
            return ProgressSummary.model_validate(raw).summary.strip()
        except (OpenRouterError, ValidationError) as exc:
            logger.warning("orchestrator summarisation failed: %s", exc)
            return None

    # ------------------------------------------------------------------ #
    # Project questions
    # ------------------------------------------------------------------ #
    async def answer_question(self, *, question: str, snapshot_text: str) -> str | None:
        client_and_model = await self.client()
        if client_and_model is None:
            return None
        client, model = client_and_model

        user = (
            f"Project snapshot:\n{_clip(snapshot_text, MAX_CONTEXT_CHARS)}\n\n"
            f"Question:\n{_clip(question, MAX_QUESTION_CHARS)}"
        )
        try:
            payload = await self._call(
                client,
                model,
                system=ANSWER_SYSTEM,
                user=user,
                schema=ANSWER_SCHEMA,
                schema_name="answer",
                max_tokens=600,
            )
        except OpenRouterError as exc:
            logger.warning("orchestrator question answering failed: %s", exc)
            return None

        answer = payload.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            return None
        return answer.strip()

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    async def _call(
        self,
        client: OpenRouterClient,
        model: str,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        schema_name: str,
        max_tokens: int,
    ) -> dict[str, Any]:
        started = time.monotonic()
        self.call_count += 1
        try:
            payload = await client.complete_json(
                model=model,
                system=system,
                user=user,
                schema=schema,
                schema_name=schema_name,
                max_tokens=max_tokens,
            )
        except OpenRouterError as exc:
            self.failure_count += 1
            self.last_error = str(exc)
            raise
        finally:
            self.last_latency_ms = int((time.monotonic() - started) * 1000)
            self.last_model = model
        self.last_error = None
        return payload


def _clip(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    cleaned = str(text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 1].rstrip()}…"
