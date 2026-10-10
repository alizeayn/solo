"""Logging configuration with best-effort secret redaction.

Any string registered with :func:`register_secret` (or matching one of the
built-in patterns) is replaced with ``***`` before a log record is emitted.
This is intentionally conservative: it is a safety net, not a licence to log
secrets.
"""

from __future__ import annotations

import logging
import re
import sys

# Patterns that commonly appear in provider credentials.
_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),          # OpenAI / OpenRouter style
    re.compile(r"sk_[A-Za-z0-9_\-]{8,}"),          # ElevenLabs style
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),  # JWT
    re.compile(r"(?i)(authorization|api[_-]?key|token|secret|password)\s*[=:]\s*\S+"),
]

# Exact secret values registered at runtime (e.g. keys loaded from settings).
_SECRET_VALUES: set[str] = set()


def register_secret(value: str | None) -> None:
    """Register a concrete secret string to be scrubbed from future logs."""
    if value and len(value) >= 6:
        _SECRET_VALUES.add(value)


def forget_secret(value: str | None) -> None:
    """Remove a previously registered secret (e.g. after a key rotation)."""
    if value:
        _SECRET_VALUES.discard(value)


def redact(text: str) -> str:
    """Return *text* with known secrets and credential-like patterns masked."""
    for secret in _SECRET_VALUES:
        if secret in text:
            text = text.replace(secret, "***")
    for pattern in _PATTERNS:
        text = pattern.sub("***", text)
    return text


class RedactionFilter(logging.Filter):
    """Logging filter that rewrites every record's message through ``redact``."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            rendered = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True
        redacted = redact(rendered)
        if redacted != rendered:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging(level: str = "INFO") -> None:
    """Install a single stderr handler with redaction applied."""
    root = logging.getLogger()
    root.setLevel(level.upper())
    # Avoid duplicate handlers when called more than once (tests, reloads).
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    handler.addFilter(RedactionFilter())
    root.addHandler(handler)
    # uvicorn access logs are noisy in tests; keep them at WARNING.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
