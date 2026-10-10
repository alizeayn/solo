"""Deterministic intent routing.

Phase 1 uses conservative, testable heuristics. Phase 3 adds an OpenRouter-
backed classifier behind the same :class:`IntentRouter.classify` contract, with
Pydantic-validated structured output. Deterministic rules are always preferred
when they are unambiguous, because they cannot hallucinate.

Precedence (highest first):

1. An explicit stop/cancel command.
2. A steering marker ("also", "instead", "wait", ...) — only while a task runs.
3. An informational question (what / why / how / explain / status / ...).
   Informational questions never start or steer a task, even when they contain
   a verb like "changed" or "add".
4. A request containing a coding verb.
5. Otherwise, plain chat.
"""

from __future__ import annotations

import re

from ..domain import Intent

#: Verbs that indicate a request to modify the project.
_CODING_VERBS = (
    "add",
    "fix",
    "implement",
    "refactor",
    "create",
    "remove",
    "delete",
    "update",
    "change",
    "write",
    "make",
    "rename",
    "debug",
    "optimi",
    "build",
    "introduce",
    "migrate",
    "install",
    "revert",
    "document",
    "test",
)

#: Leading words that mark a question seeking *information*, not an action.
_INFORMATIONAL_STARTS = (
    "what",
    "why",
    "how",
    "when",
    "where",
    "which",
    "who",
    "whose",
    "explain",
    "tell me",
    "describe",
    "summar",
    "status",
    "list ",
    "show me",
)

#: Words that indicate the user is adjusting an in-flight task.
_STEER_MARKERS = (
    "also",
    "instead",
    "actually",
    "wait",
    "hold on",
    "but ",
    "don't",
    "do not",
    "forget",
    "remember",
    "one more",
    "additionally",
    "as well",
)

_STOP_PATTERN = re.compile(
    r"^\s*(stop|cancel|abort|halt|kill|terminate)\b", re.IGNORECASE
)


class IntentRouter:
    """Classify a user message into a supported :class:`Intent`."""

    def classify(self, content: str, *, has_active_task: bool) -> Intent:
        text = (content or "").strip()
        lowered = text.lower()
        if not lowered:
            return Intent.NEEDS_CLARIFICATION

        if _STOP_PATTERN.match(lowered):
            return Intent.STOP_ACTIVE_TASK

        if has_active_task and any(marker in lowered for marker in _STEER_MARKERS):
            return Intent.STEER_ACTIVE_TASK

        is_informational = lowered.startswith(_INFORMATIONAL_STARTS)
        has_coding_verb = any(verb in lowered for verb in _CODING_VERBS)

        # Questions are answered, never executed — regardless of task state.
        if is_informational:
            return Intent.CHAT_OR_EXPLAIN

        if has_active_task:
            # A coding request while busy adjusts the running task so a second
            # writer is never started against the same project.
            if has_coding_verb or lowered.endswith("?"):
                return Intent.STEER_ACTIVE_TASK
            return Intent.CHAT_OR_EXPLAIN

        if has_coding_verb:
            return Intent.START_CODING_TASK
        return Intent.CHAT_OR_EXPLAIN
